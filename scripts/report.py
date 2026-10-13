"""`make report` (R17): regenerate every published number from evals/reports/.

README.md carries the short version between markers: the last measured value of each goal and the four
numbers of the meta-evaluation. docs/NUMEROS.md is generated whole and carries the rest: every goal at every
closed phase, the degradations and the earlier measurement of the matrix. Nothing is edited by hand;
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


def latest_table() -> str:
    """One row per goal: its value at the last phase that closed in green, with the goal's own name."""
    reports = sorted(
        (ROOT / "evals" / "reports").glob("gate-F*.json"), key=lambda p: int(re.sub(r"\D", "", p.stem))
    )
    if not reports:
        return "_Ninguna meta medida todavía._"
    goals = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text(encoding="utf-8"))["metas"]
    names = {meta["id"]: meta["nombre"] for meta in goals}
    report = json.loads(reports[-1].read_text(encoding="utf-8"))
    rows = [
        f"Último cierre en verde: F{report['milestone']}, {report['at'][:10]} "
        f"(`{reports[-1].relative_to(ROOT)}`).",
        "",
        "| Meta | Qué mide | Valor |",
        "|---|---|---|",
    ]
    rows += [
        f"| `{goal_id}` | {names.get(goal_id, '')} | {fmt(value)} |"
        for goal_id, value in sorted(report["numbers"].items())
    ]
    return "\n".join(rows)


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


def meta_summary() -> str:
    """The four numbers of the meta-evaluation against their thresholds: what README.md shows."""
    official, _, goals = _meta_documents()
    if official is None:
        return "_Meta-evaluación sin medir todavía._"
    return report_table(official, goals).split("\n\n")[0]


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
