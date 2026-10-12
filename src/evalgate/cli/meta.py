"""`evalgate meta kappa | fp | mde | sensitivity`: the evaluator, evaluated. I/O and wiring only (RULES §2).

`fp`, `mde` and `sensitivity` are recomputed from the matrix of runs (`cli.matrix`, RULES §5) and are at the
end of this file. The rest is `kappa`: the judge against the human labels (G-JUDGE-KAPPA).

What is measured is the judge OF THE SUITE: the same prompt, sampling and recorded cache that produce the
suite's `faithfulness`, asked about the very text each labelled item was built from. So the kappa published
is the kappa of the number published, not of a judge set up apart for the occasion.

Which batches count is not an argument of the command: it is written in `<labels>/kappa.yaml`, next to the
labels, so the choice is versioned and cannot be made after looking at the result. Batches listed under
`development` were used to build the judge; their agreement is reported apart and is
never the number of the goal.

Like `eval run`, a recorded run never calls a model: a verdict that is not in the cache is an error unless
`--refresh`.
"""

import hashlib
import json
from fractions import Fraction
from pathlib import Path
from typing import Any

import yaml

from evalgate.cli.matrix import read_matrix
from evalgate.evals.cache.cached import cached_answer
from evalgate.evals.cache.key import ModelCall, text_digest
from evalgate.evals.cache.store import ModelCache
from evalgate.evals.judges import client
from evalgate.evals.metrics.agreement import agreement_block, judge_label
from evalgate.evals.metrics.matrix import false_positive_block, mde_block, power_block
from evalgate.evals.prompts import load_prompt
from evalgate.evals.runner import golden_cases, judge_text, sut_outputs
from evalgate.evals.suite import BASE, parse_suite
from evalgate.gate.config import gate_config

JUDGE_PROMPT = Path("prompts/judge_faithfulness.md")
HUMAN_LABELS = {"FIEL", "NO_FIEL"}


class LabelsError(ValueError):
    """The labels, the items they were given on and the suite no longer describe the same thing."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise LabelsError(f"no existe {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _shown_digest(context: str, question: str, answer: str) -> str:
    """The digest `scripts/prepare_labels.py` gave the item: of exactly what the labeller was shown."""
    shown = {"contexto": context, "pregunta": question, "respuesta": answer}
    return (
        "sha256:" + hashlib.sha256(json.dumps(shown, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    )


def run(  # noqa: PLR0913 - wiring: every name is a file or a knob of the run
    labels_dir: Path, root: Path, goals_path: Path, out: Path, *, refresh: bool, base_url: str
) -> dict[str, Any]:
    """Measure, merge the result into the meta-eval document at `out` and return the document."""
    plan = yaml.safe_load((labels_dir / "kappa.yaml").read_text("utf-8"))
    suite_dir = root / "evals" / "suites" / str(plan["suite"])
    prompt = load_prompt(root / JUDGE_PROMPT)
    suite = parse_suite(yaml.safe_load((suite_dir / "suite.yaml").read_text("utf-8")), prompt)
    golden = {case.id: case for case in golden_cases(_jsonl(root / suite.golden_dir / "questions.jsonl"))}
    fichas = {str(row["id"]): row for row in _jsonl(root / suite.golden_dir / "corpus.jsonl")}
    cache = ModelCache(root / suite.cache_path)
    comparacion = yaml.safe_load(goals_path.read_text("utf-8"))["comparacion"]
    # The interval uses the gate's own replicates, seed and level: one place decides them (GOALS.yaml).
    config = gate_config(comparacion, yaml.safe_load((suite_dir / "gate.yaml").read_text("utf-8"))["metrics"])
    outputs: dict[str, Any] = {}

    def ratings_of(batch: int) -> dict[str, tuple[str, str]]:
        human = {str(row["item_id"]): row for row in _jsonl(labels_dir / f"tanda-{batch}.labels.jsonl")}
        ratings: dict[str, tuple[str, str]] = {}
        for key in _jsonl(labels_dir / f"tanda-{batch}.key.jsonl"):
            item_id, variant, case_id = str(key["item_id"]), str(key["variant"]), str(key["case_id"])
            if item_id not in human:
                raise LabelsError(f"tanda {batch}: {item_id} está sin etiquetar; la tanda se mide entera")
            label = human[item_id]
            if label["label"] not in HUMAN_LABELS or label["item_sha256"] != key["item_sha256"]:
                raise LabelsError(f"tanda {batch}: la etiqueta de {item_id} no corresponde a su ítem")
            if variant not in outputs:
                outputs[variant] = sut_outputs(_jsonl(root / suite.outputs_of(variant)))
            case, output = golden[case_id], outputs[variant][case_id]
            text = judge_text(prompt.body, case, output, fichas)
            context = text.split("\nFICHAS:\n", 1)[1].split("\n\nPREGUNTA: ", 1)[0]
            if _shown_digest(context, case.question, output.answer) != key["item_sha256"]:
                raise LabelsError(
                    f"tanda {batch}: {item_id} ({variant} {case_id}) ya no es lo que se etiquetó: "
                    "las salidas grabadas del sistema han cambiado"
                )
            call = ModelCall(
                "judge",
                suite.judge_id,
                prompt.model,
                suite.judge_sampling,
                prompt.version,
                prompt.sha256,
                text_digest(text),
            )
            live = None
            if refresh:
                live = lambda text=text: client.chat(base_url, prompt.model, text, suite.judge_sampling)  # noqa: E731
            ratings[item_id] = (str(label["label"]), judge_label(cached_answer(cache, call, live)))
        return ratings

    def block(batches: list[int]) -> dict[str, Any]:
        ratings: dict[str, tuple[str, str]] = {}
        for batch in batches:
            ratings.update(ratings_of(batch))
        measured = agreement_block(
            ratings, replicates=config.replicates, seed=config.seed, level=config.policy.level
        )
        return {**measured, "batches": batches}

    measurement, development = list(plan["measurement"]), list(plan.get("development", []))
    if set(measurement) & set(development):
        raise LabelsError("kappa.yaml: una tanda no puede ser a la vez de desarrollo y de medida")
    kappa = block(measurement)
    document: dict[str, Any] = json.loads(out.read_text("utf-8")) if out.exists() else {}
    document["cohens_kappa"] = {
        **kappa,
        "suite": suite.name,
        "judge": {
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "prompt_sha256": "sha256:" + prompt.sha256,
            "model": prompt.model,
            "sampling": dict(suite.judge_sampling),
        },
        "labelled_by": "samuel",
        # Batches the judge was built against. Reported so nobody mistakes them for the measurement.
        "development": block(development) if development else None,
    }
    document["n_etiquetados"] = kappa["n"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    return document


def _merged(out: Path, blocks: dict[str, Any]) -> dict[str, Any]:
    """Write `blocks` into the meta-eval document at `out`, keeping every other block, and return it."""
    document: dict[str, Any] = json.loads(out.read_text("utf-8")) if out.exists() else {}
    document.update(blocks)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    return document


class _Measured:
    """The matrix file, split the way the three goals read it, and the gate that is being measured: the
    suite's own rules under GOALS.yaml `comparacion`, exactly what `eval compare` would use."""

    def __init__(self, matrix_path: Path, root: Path, goals_path: Path) -> None:
        self.metadata, runs = read_matrix(matrix_path)
        gate_path = root / "evals" / "suites" / str(self.metadata["suite"]) / "gate.yaml"
        self.config = gate_config(
            yaml.safe_load(goals_path.read_text("utf-8"))["comparacion"],
            yaml.safe_load(gate_path.read_text("utf-8"))["metrics"],
        )
        self.baseline = str(self.metadata["baseline"])
        self.h0: dict[str, Any] = {}
        self.degradations: dict[str, dict[str, Any]] = {}
        for run_id, described in self.metadata["runs"].items():
            if run_id not in runs:
                raise LabelsError(f"{matrix_path}: falta la ejecución {run_id} que su cabecera declara")
            variant = str(described["variant"])
            (self.h0 if variant == BASE else self.degradations.setdefault(variant, {}))[run_id] = runs[run_id]
        self.provenance = {
            "matrix": str(matrix_path),
            "matrix_sha256": "sha256:" + hashlib.sha256(matrix_path.read_bytes()).hexdigest(),
            "suite": self.metadata["suite"],
            "blocking_metrics": [rule.metric for rule in self.config.rules if rule.blocking],
            "replicates": self.config.replicates,
            "seed": self.config.seed,
        }


def fp(matrix_path: Path, root: Path, goals_path: Path, out: Path) -> dict[str, Any]:
    """G-GATE-FP, recomputed from the matrix. No model is called."""
    measured = _Measured(matrix_path, root, goals_path)
    block = false_positive_block(measured.h0, measured.baseline, measured.config)
    return _merged(
        out,
        {
            "fp_rate_baseline_fixed": {**block, **measured.provenance},
            "n_decisiones": block["n"],
            "fuente_de_ruido": measured.metadata["noise_source"],
        },
    )


def mde(matrix_path: Path, root: Path, goals_path: Path, out: Path) -> dict[str, Any]:
    """G-GATE-MDE, recomputed from the matrix. No model is called."""
    measured = _Measured(matrix_path, root, goals_path)
    block = mde_block(measured.h0, measured.config.rules, Fraction(measured.metadata["mde_percentile"]))
    return _merged(
        out,
        {"mde_pp": {**block, **measured.provenance}, "n_casos_subsuite": measured.metadata["n_cases"]},
    )


def sensitivity(matrix_path: Path, root: Path, goals_path: Path, out: Path) -> dict[str, Any]:
    """G-GATE-POWER, recomputed from the matrix. The minimum detectable effect it is relative to is the one
    the same matrix gives, computed here and not read from a document somebody could have edited."""
    measured = _Measured(matrix_path, root, goals_path)
    effect = mde_block(measured.h0, measured.config.rules, Fraction(measured.metadata["mde_percentile"]))
    block = power_block(
        measured.h0,
        measured.baseline,
        measured.degradations,
        measured.config,
        mde_pp=effect["point"],
        min_size_over_mde=Fraction(measured.metadata["power_min_size_over_mde"]),
    )
    return _merged(out, {"power": {**block, **measured.provenance}})
