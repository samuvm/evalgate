"""`evalgate meta run-matrix`: the runs the gate itself is measured on (RULES §5). I/O and wiring only.

The suite's `matrix.yaml` says what is executed: the calibration subsuite, run many times with a declared
source of noise (the system above temperature 0 and a different seed per run), once per variant of the
system. The judge is called live every time: no cache is read or written, because a cached verdict would
turn fifty runs into one (G-GATE-FP).

Two steps, so a night of work survives an interruption:

1. **record**: each run is one file, `<raw>/<run_id>.jsonl`, with what the system answered and what the judge
   said, case by case. A run whose file is complete is never executed again.
2. **build**: every run is scored by the suite's own `evals.runner.evaluate` and the result is persisted as
   `(run_id, case_id, metrica, valor)` in one Parquet file, with what produced it in the file's metadata.

Everything the meta-evaluation publishes afterwards is recomputed offline from that file (`cli.meta`).
"""

import hashlib
import json
import platform
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from fractions import Fraction
from pathlib import Path
from typing import Any

import httpx
import pyarrow as pa
import pyarrow.parquet as pq
import yaml

from evalgate.cli.eval_run import sut_stdout
from evalgate.evals.judges import client
from evalgate.evals.prompts import load_prompt
from evalgate.evals.runner import GoldenCase, SutOutput, evaluate, golden_cases, judge_text, sut_outputs
from evalgate.evals.suite import BASE, Suite, parse_suite

JUDGE_PROMPT = Path("prompts/judge_faithfulness.md")
DATA_DIR = Path(".run/matrix/data")  # the subsuite as the example app reads it: local, rebuilt every time
METADATA_KEY = b"evalgate"
JUDGE_ATTEMPTS = 3
_PLAN_KEYS = {
    "suite",
    "cases",
    "noise",
    "seed_from",
    "runs",
    "baseline",
    "mde_percentile",
    "power_min_size_over_mde",
}
_OPTIONAL_PLAN_KEYS = {"judge"}
ALL_CASES = "all"  # `cases: all`: the whole golden set instead of a chosen subsuite
JUDGE_METRICS = ("faithfulness", "juez_ilegible")  # what a plan with `judge: off` does not measure

Matrix = dict[str, dict[str, dict[str, float]]]  # run → metric → case → value


class MatrixError(ValueError):
    """The plan, the recorded runs or the matrix file do not describe one same experiment."""


@dataclass(frozen=True, slots=True)
class RunSpec:
    run_id: str
    variant: str
    seed: int


@dataclass(frozen=True, slots=True)
class Plan:
    suite: str
    cases_path: str
    noise: Mapping[str, str]
    seed_from: int
    runs: Mapping[str, int]  # variant → how many runs
    baseline: str
    mde_percentile: Fraction
    power_min_size_over_mde: Fraction
    sha256: str
    # False (`judge: off`): the judge is not called and its metrics are not in the matrix. For a suite whose
    # judge metric is retired from the gate, calling it thousands of times measures nothing the gate uses.
    judge: bool = True

    def specs(self) -> list[RunSpec]:
        return [
            RunSpec(f"{variant}-{number:02d}", variant, self.seed_from + number)
            for variant, count in self.runs.items()
            for number in range(count)
        ]


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def load_plan(path: Path) -> Plan:
    node = yaml.safe_load(path.read_text("utf-8"))
    if not isinstance(node, dict) or not _PLAN_KEYS <= node.keys() <= _PLAN_KEYS | _OPTIONAL_PLAN_KEYS:
        raise MatrixError(
            f"{path}: debe declarar {', '.join(sorted(_PLAN_KEYS))} y, si acaso, "
            f"{', '.join(sorted(_OPTIONAL_PLAN_KEYS))}"
        )
    if node.get("judge", "live") not in {"live", "off"}:
        raise MatrixError(f"{path}: `judge` es live u off, no {node['judge']!r}")
    runs = {str(variant): int(count) for variant, count in node["runs"].items()}
    plan = Plan(
        suite=str(node["suite"]),
        cases_path=str(node["cases"]),
        noise={str(key): str(value) for key, value in node["noise"].items()},
        seed_from=int(node["seed_from"]),
        runs=runs,
        baseline=str(node["baseline"]),
        # Through `str`: 1.5 written in YAML is the decimal 1.5, not the nearest binary float.
        mde_percentile=Fraction(str(node["mde_percentile"])),
        power_min_size_over_mde=Fraction(str(node["power_min_size_over_mde"])),
        sha256=_digest(path),
        judge=node.get("judge", "live") == "live",
    )
    if not plan.noise:
        raise MatrixError(f"{path}: sin fuente de ruido todas las ejecuciones serían la misma")
    if plan.baseline not in {spec.run_id for spec in plan.specs() if spec.variant == BASE}:
        raise MatrixError(f"{path}: la línea base {plan.baseline!r} no es una ejecución de `{BASE}`")
    return plan


@dataclass(frozen=True, slots=True)
class Experiment:
    plan: Plan
    suite: Suite
    golden: list[GoldenCase]  # the calibration cases, in golden order
    fichas: dict[str, dict[str, Any]]
    golden_sha256: str


def load_experiment(plan_path: Path, root: Path) -> Experiment:
    plan = load_plan(plan_path)
    suite_dir = root / "evals" / "suites" / plan.suite
    suite = parse_suite(
        yaml.safe_load((suite_dir / "suite.yaml").read_text("utf-8")), load_prompt(root / JUDGE_PROMPT)
    )
    for variant in plan.runs:
        suite.outputs_of(variant)  # raises on a variant the suite does not declare
    golden_path = root / suite.golden_dir / "questions.jsonl"
    golden = golden_cases(_jsonl(golden_path))
    if plan.cases_path != ALL_CASES:
        calibration = json.loads((root / plan.cases_path).read_text("utf-8"))
        if calibration["golden_sha256"] != _digest(golden_path):
            raise MatrixError(f"{plan.cases_path} se eligió sobre otro golden set: no se mezclan")
        chosen = set(calibration["cases"])
        golden = [case for case in golden if case.id in chosen]
        if len(golden) != len(chosen):
            raise MatrixError(f"{plan.cases_path} nombra casos que no están en el golden set")
    fichas = {str(row["id"]): row for row in _jsonl(root / suite.golden_dir / "corpus.jsonl")}
    return Experiment(plan, suite, golden, fichas, _digest(golden_path))


def _knobs(experiment: Experiment, spec: RunSpec) -> dict[str, str]:
    """The environment of one run: the noise, then what the variant changes, then this run's seed."""
    return {**experiment.plan.noise, **experiment.suite.variants[spec.variant], "RAG_SEED": str(spec.seed)}


def _complete(path: Path, experiment: Experiment) -> bool:
    if not path.exists():
        return False
    rows = _jsonl(path)
    return [row["id"] for row in rows] == [case.id for case in experiment.golden] and (
        not experiment.plan.judge or all("verdict" in row for row in rows)
    )


def _verdict(base_url: str, model: str, text: str, sampling: Mapping[str, float | int | str]) -> str:
    for attempt in range(JUDGE_ATTEMPTS):
        try:
            return client.chat(base_url, model, text, sampling)[0]
        except httpx.HTTPError:
            if attempt == JUDGE_ATTEMPTS - 1:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def record(plan_path: Path, root: Path, raw_dir: Path, base_url: str, progress: Callable[[str], None]) -> int:
    """Execute every run of the plan that is not recorded yet. Returns how many were executed now."""
    experiment = load_experiment(plan_path, root)
    suite, prompt = experiment.suite, experiment.suite.judge_prompt
    data_dir = root / DATA_DIR
    data_dir.mkdir(parents=True, exist_ok=True)
    chosen = {case.id for case in experiment.golden}
    questions = [row for row in _jsonl(root / suite.golden_dir / "questions.jsonl") if row["id"] in chosen]
    (data_dir / "questions.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in questions), "utf-8"
    )
    (data_dir / "corpus.jsonl").write_bytes((root / suite.golden_dir / "corpus.jsonl").read_bytes())
    raw_dir.mkdir(parents=True, exist_ok=True)

    specs = experiment.plan.specs()
    executed = 0
    for position, spec in enumerate(specs, 1):
        path = raw_dir / f"{spec.run_id}.jsonl"
        if _complete(path, experiment):
            continue
        started = time.monotonic()
        variant_suite = replace(suite, generator_model=suite.model_of(spec.variant))
        printed = sut_stdout(variant_suite, _knobs(experiment, spec), data_dir, root, base_url)
        rows = [json.loads(line) for line in printed.splitlines() if line.strip()]
        outputs = sut_outputs(rows)
        if [row["id"] for row in rows] != [case.id for case in experiment.golden]:
            raise MatrixError(f"{spec.run_id}: el sistema no respondió a los casos pedidos, en su orden")
        if experiment.plan.judge:
            for row, case in zip(rows, experiment.golden, strict=True):
                text = judge_text(prompt.body, case, outputs[case.id], experiment.fichas)
                # Live, every time: no cache is read or written in this experiment (G-GATE-FP).
                row["verdict"] = _verdict(base_url, prompt.model, text, suite.judge_sampling)
        partial = path.with_suffix(".partial")
        partial.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")
        partial.replace(path)
        executed += 1
        progress(
            f"{position}/{len(specs)} {spec.run_id} semilla {spec.seed} · {time.monotonic() - started:.0f} s"
        )
    return executed


def build(plan_path: Path, root: Path, raw_dir: Path, out: Path) -> dict[str, Any]:
    """Score every recorded run and persist the matrix. Refuses a plan that is not recorded whole."""
    experiment = load_experiment(plan_path, root)
    suite, prompt, plan = experiment.suite, experiment.suite.judge_prompt, experiment.plan
    specs = plan.specs()
    if missing := [
        spec.run_id for spec in specs if not _complete(raw_dir / f"{spec.run_id}.jsonl", experiment)
    ]:
        raise MatrixError(f"faltan {len(missing)} ejecuciones por grabar: {', '.join(missing[:5])}")

    columns: dict[str, list[Any]] = {"run_id": [], "case_id": [], "metrica": [], "valor": []}
    for spec in specs:
        rows = _jsonl(raw_dir / f"{spec.run_id}.jsonl")
        verdicts = {str(row["id"]): str(row.get("verdict", "")) for row in rows}

        def recorded(case: GoldenCase, _output: SutOutput, verdicts: dict[str, str] = verdicts) -> str:
            return verdicts[case.id]

        scores = evaluate(experiment.golden, sut_outputs(rows), recorded)
        if not plan.judge:
            for metric in JUDGE_METRICS:
                del scores[metric]
        for metric in sorted(scores):
            for case_id, value in sorted(scores[metric].items()):
                columns["run_id"].append(spec.run_id)
                columns["case_id"].append(case_id)
                columns["metrica"].append(metric)
                columns["valor"].append(float(value))

    metadata = {
        "suite": suite.name,
        "plan": str(plan_path),
        "plan_sha256": plan.sha256,
        "golden_sha256": experiment.golden_sha256,
        "n_cases": len(experiment.golden),
        "baseline": plan.baseline,
        "noise_source": (
            f"sistema bajo prueba con {', '.join(f'{k}={v}' for k, v in sorted(plan.noise.items()))} y "
            f"semilla distinta por ejecución (RAG_SEED = {plan.seed_from} + nº de ejecución); "
            + (
                "juez llamado en vivo en cada caso, sin caché"
                if plan.judge
                else "sin juez: sus métricas no se miden"
            )
        ),
        "mde_percentile": str(plan.mde_percentile),
        "power_min_size_over_mde": str(plan.power_min_size_over_mde),
        "sut_model": suite.generator_model,
        "judge": {
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "prompt_sha256": "sha256:" + prompt.sha256,
            "model": prompt.model,
            "sampling": dict(suite.judge_sampling),
        }
        if plan.judge
        else None,
        "runs": {
            spec.run_id: {
                "variant": spec.variant,
                "seed": spec.seed,
                "knobs": _knobs(experiment, spec),
                "raw_sha256": _digest(raw_dir / f"{spec.run_id}.jsonl"),
            }
            for spec in specs
        },
        "raw_dir": str(raw_dir),
        "hardware": f"{platform.machine()} · {platform.platform()}",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    table = pa.table(
        columns,
        schema=pa.schema(
            [
                ("run_id", pa.string()),
                ("case_id", pa.string()),
                ("metrica", pa.string()),
                ("valor", pa.float64()),
            ],
            metadata={METADATA_KEY: json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode()},
        ),
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(table, out, compression="zstd")
    return metadata


def read_matrix(path: Path) -> tuple[dict[str, Any], Matrix]:
    """The matrix file as (what produced it, run → metric → case → value)."""
    if not path.exists():
        raise MatrixError(f"no existe {path}: se crea con `evalgate meta run-matrix`")
    table = pq.read_table(path)
    packed = (table.schema.metadata or {}).get(METADATA_KEY)
    if packed is None:
        raise MatrixError(f"{path} no dice qué experimento lo produjo")
    matrix: Matrix = {}
    for row in table.to_pylist():
        cases = matrix.setdefault(row["run_id"], {}).setdefault(row["metrica"], {})
        if row["case_id"] in cases:
            raise MatrixError(f"{path}: {row['run_id']} {row['metrica']} {row['case_id']} está repetido")
        cases[row["case_id"]] = float(row["valor"])
    return json.loads(packed), matrix
