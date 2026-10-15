"""`make report` (R17): regenerate every published number from evals/reports/.

README.md carries the short version between markers, in English: the last measured value of each goal and the
four numbers of the meta-evaluation. docs/NUMEROS.md is generated whole and carries the rest: every goal at
every closed phase, the degradations and the earlier measurement of the matrix. Nothing is edited by hand;
`--check` fails if either file differs from what would be generated (scripts/rules/readme_numbers.py).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

import yaml

from evalgate.cli.meta import report_table
from gatelib import ROOT

README = ROOT / "README.md"
NUMBERS = ROOT / "docs" / "NUMEROS.md"
START, END = "<!-- evalgate:numbers:start -->", "<!-- evalgate:numbers:end -->"
META_START, META_END = "<!-- evalgate:meta:start -->", "<!-- evalgate:meta:end -->"


def fmt(value: Any) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={fmt(v)}" for k, v in value.items())
    if isinstance(value, float):
        return f"{value:.2f}".replace(".", ",")
    return str(value)


def table() -> str:
    reports = sorted(
        (ROOT / "evals" / "reports").glob("gate-F*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem))
    )
    if not reports:
        return "_Ninguna meta medida todavía: F0 no tenía metas bloqueantes._"
    rows = ["| Fase | Meta | Valor | Cerrada | Artefacto |", "|---|---|---|---|---|"]
    for path in reports:
        report = json.loads(path.read_text(encoding="utf-8"))
        for goal_id, value in sorted(report["numbers"].items()):
            phase, day, source = report["milestone"], report["at"][:10], path.relative_to(ROOT)
            rows.append(f"| F{phase} | `{goal_id}` | {fmt(value)} | {day} | `{source}` |")
    return "\n".join(rows)


# README.md is in English; GOALS.yaml names its goals in Spanish. Same ids, so a goal missing here shows its
# Spanish name instead of disappearing.
README_NAMES = {
    "G-ADOPTION": "Adoption through one environment variable, no code changes (diff lines)",
    "G-CACHE-HIT": "Marginal cost of re-running the suite",
    "G-CACHE-INVAL": "The judge cache key invalidates exactly what it should",
    "G-DETERMINISM": "Determinism of `eval compare`",
    "G-DISCONNECT": "Accounting when the client disconnects",
    "G-FUNC-COV": "Public functions without a unit test (plus property tests in pricing/ and stats/)",
    "G-LAT-PROXY": "p95 proxy overhead, non-streaming (ms)",
    "G-LAT-TTFT": "p95 time-to-first-token overhead, streaming (ms)",
    "G-LINE-COV": "Line coverage of the testable packages (%)",
    "G-MUTATION": "Killed mutants in the TDD packages (%)",
    "G-OPENAI-CONTRACT": "Compatibility with OpenAI's published schema",
    "G-OTEL-CONTRACT": "Spans conforming to the pinned OTel GenAI contract",
    "G-PRICE-REPRO": "Reproducibility of historical cost reports (EUR difference)",
    "G-TOKENS-EXACT": "Exact token accounting, non-streaming",
    "G-TOKENS-STREAM": "Token accounting, streaming",
    "G-TRACE-0": "Zero spans lost with a healthy store",
    "G-TRACE-DEGRADE": "Graceful degradation with the store down (p95 delta, ms)",
}


def fmt_en(value: Any, digits: int = 2) -> str:
    if isinstance(value, dict):
        return ", ".join(f"{k}={fmt_en(v)}" for k, v in value.items())
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def latest_table() -> str:
    """One row per goal, as README.md shows it: its value at the last phase that closed in green."""
    reports = sorted(
        (ROOT / "evals" / "reports").glob("gate-F*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem))
    )
    if not reports:
        return "_No goal measured yet._"
    goals = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text(encoding="utf-8"))["metas"]
    names = {meta["id"]: README_NAMES.get(meta["id"], meta["nombre"]) for meta in goals}
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    rows = [
        f"Last phase closed in green: F{report['milestone']}, {report['at'][:10]} "
        f"(`{reports[-1].relative_to(ROOT)}`).",
        "",
        "| Goal | What it measures | Value |",
        "|---|---|---|",
    ]
    rows += [
        f"| `{goal_id}` | {names.get(goal_id, '')} | {fmt_en(value)} |"
        for goal_id, value in sorted(report["numbers"].items())
    ]
    return "\n".join(rows)


def meta_summary() -> str:
    """The four numbers of the meta-evaluation against their GOALS.yaml thresholds, in English. The verdict
    is on the full value, never on the rounded one."""
    official, _, goals = _meta_documents()
    if official is None:
        return "_Meta-evaluation not measured yet._"
    thresholds = {meta["id"]: meta["umbral"] for meta in goals["metas"]}
    kappa, rate = official["cohens_kappa"], official["fp_rate_baseline_fixed"]
    effect, power = official["mde_pp"], official["power"]
    kappa_ci, wilson = kappa["ci95_bootstrap"], rate["wilson_95"]
    rows = [
        (
            "G-JUDGE-KAPPA",
            kappa["point"],
            2,
            f"95% CI [{fmt_en(kappa_ci[0])}, {fmt_en(kappa_ci[1])}] · {kappa['n']} human labels · "
            f"raw agreement {fmt_en(kappa['raw_agreement'])}",
        ),
        (
            "G-GATE-FP",
            rate["point"],
            3,
            f"Wilson 95% [{fmt_en(wilson[0], 3)}, {fmt_en(wilson[1], 3)}] · "
            f"{rate['blocked']} blocks in {rate['n']} decisions against `{rate['baseline']}`",
        ),
        (
            "G-GATE-MDE",
            effect["point"],
            2,
            f"percentage points, on `{effect['limiting_metric']}` · {official['n_casos_subsuite']} cases · "
            f"{effect['n_pairs']} pairs from {effect['n_runs']} runs",
        ),
        (
            "G-GATE-POWER",
            power["min_over_degradations"],
            2,
            f"minimum over degradations of size ≥ {fmt_en(power['required_size_pp'])} pp · "
            f"minimum over all {len(power['per_degradation'])}: {fmt_en(power['min_over_all'])}",
        ),
    ]
    holds = {">=": lambda v, b: v >= b, "<=": lambda v, b: v <= b, "==": lambda v, b: v == b}
    lines = ["| Goal | Measured | Threshold | Met? | Detail |", "|---|---|---|---|---|"]
    for goal_id, value, digits, detail in rows:
        threshold = thresholds[goal_id]
        met = value is not None and holds[threshold["operador"]](value, threshold["valor"])
        shown = "not measured" if value is None else fmt_en(value, digits)
        bound = fmt_en(float(threshold["valor"]))
        verdict = "yes" if met else "**no**"
        lines.append(f"| `{goal_id}` | {shown} | {threshold['operador']} {bound} | {verdict} | {detail} |")
    return "\n".join(lines)


def _meta_documents() -> tuple[dict[str, Any] | None, list[tuple[str, dict[str, Any]]], dict[str, Any]]:
    """The official meta-eval document, the earlier measurements of the matrix, and GOALS."""
    path = ROOT / "evals" / "reports" / "meta-eval.json"
    goals = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text(encoding="utf-8"))
    if not path.exists():
        return None, [], goals
    earlier = []
    for other in sorted(path.parent.glob("meta-eval-*.json")):
        document = json.loads(other.read_text(encoding="utf-8"))
        if "fp_rate_baseline_fixed" in document:  # else: another document of the judge, not of the matrix
            earlier.append((str(other.relative_to(ROOT)), document))
    return json.loads(path.read_text(encoding="utf-8")), earlier, goals


def meta_table() -> str:
    """The whole meta-evaluation (F7): the official measurement with its degradations and, below, every
    earlier one. Rendered by the same function `evalgate meta report` prints."""
    official, earlier, goals = _meta_documents()
    if official is None:
        return "_Meta-evaluación sin medir todavía._"
    shown = report_table(official, goals)
    for source, document in earlier:
        shown += (
            f"\n\n**Medida anterior, publicada tal cual** · {document['n_casos_subsuite']} casos · "
            f"`{source}`\n\n" + report_table(document, goals, matrix_only=True)
        )
    return shown


def numbers_document() -> str:
    return "\n".join(
        [
            "# Números medidos",
            "",
            "Generado por `make report` desde `evals/reports/`. No se edita a mano (regla R17).",
            "Hardware de referencia: MacBook Pro M4 Max, 36 GB de memoria unificada.",
            "",
            "## La puerta, medida (meta-evaluación)",
            "",
            "`evalgate meta report --check` vuelve a calcular la medida oficial desde las etiquetas humanas",
            "y la matriz de ejecuciones, sin llamar a ningún modelo. La matriz se midió dos veces; antes de",
            "ejecutar la segunda quedó escrito que sus tres números sustituirían a los de la primera,",
            "salieran como salieran.",
            "",
            meta_table(),
            "",
            "## Cada meta en cada fase cerrada",
            "",
            table(),
            "",
        ]
    )


def _between(readme: str, start: str, end: str, body: str) -> str:
    pattern = re.compile(re.escape(start) + r".*?" + re.escape(end), re.S)
    if not pattern.search(readme):
        raise SystemExit(f"README.md sin marcadores {start} … {end}")
    return pattern.sub(lambda _: f"{start}\n{body}\n{end}", readme)


def render(readme: str) -> str:
    return _between(_between(readme, START, END, latest_table()), META_START, META_END, meta_summary())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = README.read_text(encoding="utf-8")
    expected = {README: render(current), NUMBERS: numbers_document()}
    if args.check:
        stale = [
            path for path, text in expected.items() if not path.exists() or path.read_text("utf-8") != text
        ]
        if stale:
            names = ", ".join(str(path.relative_to(ROOT)) for path in stale)
            print(f"R17 FALLA · {names} no coincide con evals/reports/: `make report`", file=sys.stderr)
            return 1
        print("R17 ok · README.md y docs/NUMEROS.md coinciden con evals/reports/")
        return 0
    for path, text in expected.items():
        path.write_text(text, encoding="utf-8")
    print("README.md y docs/NUMEROS.md regenerados desde evals/reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
