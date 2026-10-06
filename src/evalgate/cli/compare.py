"""`evalgate eval compare BASE HEAD`: the gate, as a command. I/O and wiring only (RULES §2), held by
tests/contract/test_report_schema.py.

Reads two eval reports (docs/CONTRACTS/eval-report.schema.json) and, for each, the per-case values its
metrics point to (`metrics[].raw_path`, relative to the report: a JSON list of `{case_id, value}`). Judges
HEAD against BASE with `gate.compare` and writes HEAD's report with the `comparison` block added.

Nothing here decides: the parameters come from docs/GOALS.yaml `comparacion` and the suite's `gate.yaml`
(`gate.config`), the statistics from `stats/`, the verdict from `gate.decision`.
"""

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evalgate.gate.compare import Comparison, Run, compare, comparison_block
from evalgate.gate.config import GateConfigError, gate_config


class NotComparable(ValueError):
    """The two reports cannot be compared at all: different suite or different dataset."""


def _report(path: Path) -> tuple[dict[str, Any], Run]:
    document: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    run: dict[str, dict[str, float]] = {}
    for metric in document["metrics"]:
        if "raw_path" not in metric:
            continue  # a metric with no per-case detail cannot be paired; a rule that needs it will say so
        rows = json.loads((path.parent / metric["raw_path"]).read_text(encoding="utf-8"))
        run[metric["id"]] = {row["case_id"]: float(row["value"]) for row in rows}
    return document, run


def run(base_path: Path, head_path: Path, gate_path: Path, goals_path: Path, out: Path) -> Comparison:
    """Compare, write the report to `out` and return the comparison. Raises `NotComparable`,
    `GateConfigError` or the gate's own errors instead of producing a report it cannot stand behind."""
    base_doc, base_run = _report(base_path)
    head_doc, head_run = _report(head_path)
    for field, base_value, head_value in (
        ("suite", base_doc["suite"], head_doc["suite"]),
        ("dataset.sha256", base_doc["dataset"]["sha256"], head_doc["dataset"]["sha256"]),
    ):
        if base_value != head_value:
            raise NotComparable(
                f"{field} distinto: base {base_value!r}, head {head_value!r}. No se comparan."
            )

    goals = yaml.safe_load(goals_path.read_text(encoding="utf-8"))
    rules = yaml.safe_load(gate_path.read_text(encoding="utf-8"))
    if not isinstance(rules, dict) or "metrics" not in rules:
        raise GateConfigError(f"{gate_path}: falta la lista `metrics`")
    config = gate_config(goals["comparacion"], rules["metrics"])
    comparison = compare(base_run, head_run, config)

    block = comparison_block(comparison, base_doc["run_id"])
    identity = json.dumps([base_doc["run_id"], head_doc["run_id"], block], sort_keys=True)
    document = {
        **head_doc,
        # Deterministic: the same two reports under the same configuration are the same comparison.
        "run_id": f"compare-{hashlib.sha256(identity.encode()).hexdigest()[:16]}",
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {**head_doc["environment"], "deterministic": True, "seed": config.seed},
        "comparison": block,
    }
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return comparison


def table(comparison: Comparison) -> str:
    """The output a person reads in CI: one line per metric, and why it blocks."""
    lines = [f"{'métrica':22} {'base':>7} {'head':>7} {'delta':>8}  {'IC95':^19} {'p':>7}  veredicto"]
    for metric in comparison.metrics:
        verdict = metric.verdict
        if verdict.blocking:
            why = "BLOQUEA: " + " y ".join(
                reason
                for reason, applies in (
                    ("IC entero del lado malo", verdict.significant),
                    ("cae bajo su umbral absoluto", verdict.fell_below_absolute),
                )
                if applies
            )
        else:
            why = "ok" if metric.rule.blocking else "solo informa"
        lines.append(
            f"{metric.rule.metric:22} {metric.base_value:7.3f} {metric.head_value:7.3f} "
            f"{metric.delta:+8.3f}  [{metric.ci_low:+.3f}, {metric.ci_high:+.3f}] "
            f"{float(verdict.p_value):7.4f}  {why}"
        )
    correction = comparison.correction or "ninguna (tres métricas bloqueantes o menos)"
    lines.append(
        f"bootstrap pareado · {comparison.replicates} réplicas · semilla {comparison.seed} · "
        f"corrección: {correction}"
    )
    lines.append(f"decisión: {comparison.outcome.upper()}")
    return "\n".join(lines)
