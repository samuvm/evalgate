"""`evalgate eval run --suite X [--refresh]`: an eval run. I/O and wiring only (RULES §2).

Two modes, and the difference is the whole point:

- **recorded** (default, `make eval`): reads the outputs of the system and the judge's verdicts from the
  repository. No model is called; a verdict that is not recorded is an error. Deterministic and free, so it
  can run in the gate.
- **refresh** (`--refresh`, `make eval-refresh`): runs the system under test against the model and calls the
  judge for whatever is not cached. Never in the gate.

Everything that decides lives elsewhere: `evals.runner` scores, `evals.report` builds the document,
`evals.suite` refuses a judge that is the generator (R12).
"""

import hashlib
import json
import os
import platform
import subprocess  # nosec B404 - launches this repository's own example client, see record_sut
import sys
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evalgate.evals.cache.cached import cached_answer
from evalgate.evals.cache.key import ModelCall, text_digest
from evalgate.evals.cache.store import CacheStats, ModelCache
from evalgate.evals.judges import client
from evalgate.evals.prompts import load_prompt
from evalgate.evals.report import eval_report, raw_rows
from evalgate.evals.runner import GoldenCase, SutOutput, evaluate, golden_cases, judge_text, sut_outputs
from evalgate.evals.suite import BASE, Suite, parse_suite

JUDGE_PROMPT = Path("prompts/judge_faithfulness.md")
RUNS_LOG = Path(".run/cache-runs.jsonl")  # local state: the cost of each run, for `evalgate cache stats`


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def record_sut(suite: Suite, variant: str, root: Path, base_url: str) -> None:
    """Run one variant of the system under test over the golden set and record what it printed. It is a
    CLIENT: launched as a separate process with environment variables, never imported (R13)."""
    out = root / suite.outputs_of(variant)
    out.parent.mkdir(parents=True, exist_ok=True)
    env = {
        # No RAG_* leaks in from the shell: a variant is exactly the knobs the suite declares for it.
        **{key: value for key, value in os.environ.items() if not key.startswith("RAG_")},
        "RAG_DATA": str(root / suite.golden_dir),
        "OPENAI_BASE_URL": base_url,
        "RAG_MODEL": suite.generator_model,
        **suite.variants[variant],
    }
    done = subprocess.run(  # noqa: S603  # nosec B603 - fixed script of this repository, no user input
        [sys.executable, str(root / "examples" / "rag-app" / "rag_app.py")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if done.returncode != 0:
        raise RuntimeError(f"el sistema bajo prueba falló (exit {done.returncode}):\n{done.stderr[-2000:]}")
    out.write_text(done.stdout, encoding="utf-8")


def run(  # noqa: PLR0913 - the knobs of a run, all named at the call
    suite_dir: Path, root: Path, out_dir: Path, *, refresh: bool, base_url: str, variant: str = BASE
) -> tuple[dict[str, Any], CacheStats]:
    """Run one variant of the suite, write its report with its per-case files, return report and stats.

    The base variant is `<out_dir>/<suite>.json`; any other, `<out_dir>/<suite>-<variant>.json`. Same suite,
    same golden set, same judge: only the system changes, so the gate can compare the two reports.
    """
    declared = parse_suite(
        yaml.safe_load((suite_dir / "suite.yaml").read_text("utf-8")), load_prompt(root / JUDGE_PROMPT)
    )
    # From here on `suite` is the variant being run: its model and its recorded outputs.
    suite = replace(
        declared, generator_model=declared.model_of(variant), sut_outputs=declared.outputs_of(variant)
    )
    name = suite.name if variant == BASE else f"{suite.name}-{variant}"
    golden_path = root / suite.golden_dir / "questions.jsonl"
    golden = golden_cases(_jsonl(golden_path))
    fichas = {str(row["id"]): row for row in _jsonl(root / suite.golden_dir / "corpus.jsonl")}
    if refresh:
        record_sut(declared, variant, root, base_url)
    outputs = sut_outputs(_jsonl(root / suite.sut_outputs))
    cache = ModelCache(root / suite.cache_path)
    prompt = suite.judge_prompt

    def judge(case: GoldenCase, output: SutOutput) -> str:
        text = judge_text(prompt.body, case, output, fichas)
        call = ModelCall(
            "judge",
            suite.judge_id,
            prompt.model,
            suite.judge_sampling,
            prompt.version,
            prompt.sha256,
            text_digest(text),
        )
        live = (lambda: client.chat(base_url, prompt.model, text, suite.judge_sampling)) if refresh else None
        return cached_answer(cache, call, live)

    scores = evaluate(golden, outputs, judge)
    stats = cache.stats()
    report = eval_report(
        suite,
        scores,
        stats,
        {
            "golden_sha256": _digest(golden_path),
            "sut_outputs_sha256": _digest(root / suite.sut_outputs),
            "n_cases": len(golden),
            "n_negative_cases": sum(not case.positive for case in golden),
            "hardware": f"{platform.machine()} · {platform.platform()}",
            "python": platform.python_version(),
            "deterministic": not refresh,
            "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "raw_dir": name,
        },
    )
    raw_dir = out_dir / name
    raw_dir.mkdir(parents=True, exist_ok=True)
    for metric, rows in raw_rows(scores).items():
        (raw_dir / f"{metric}.json").write_text(
            json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8"
        )
    (out_dir / f"{name}.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", "utf-8")

    log = root / RUNS_LOG
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({"suite": name, "at": report["created_at"], **_cost(stats)}) + "\n")
    return report, stats


def _cost(stats: CacheStats) -> dict[str, Any]:
    return {
        "hits": stats.hits,
        "misses": stats.misses,
        "spent_tokens": stats.spent_tokens,
        "saved_tokens": stats.saved_tokens,
        "hit_rate": stats.hit_rate,
        "marginal_cost_ratio": stats.marginal_cost_ratio,
    }


def cache_stats(suite: str, root: Path, out: Path) -> dict[str, Any]:
    """G-CACHE-HIT: the cost of the last two runs of `suite`, and of the last run that had to pay (cold).

    `second_run.marginal_cost_ratio` is what the goal reads: what the second run cost over what it would
    have cost with no cache. Written to `out`.
    """
    log = root / RUNS_LOG
    runs = [row for row in _jsonl(log) if row["suite"] == suite] if log.exists() else []
    if len(runs) < 2:
        raise ValueError(
            f"hacen falta dos ejecuciones de `{suite}` para medir el coste marginal; hay {len(runs)}"
        )
    paid = [row for row in runs if row["misses"] > 0]
    document = {
        "suite": suite,
        "first_run": runs[-2],
        "second_run": runs[-1],
        "cold_run": paid[-1] if paid else None,
    }
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return document
