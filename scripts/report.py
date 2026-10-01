"""`make report` (R17): regenerate the numbers table of README.md from evals/reports/gate-F*.json.

The table lives between two markers and is never edited by hand. `--check` fails if README.md differs from
what would be generated (scripts/rules/readme_numbers.py calls it in the gate).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

from gatelib import ROOT

README = ROOT / "README.md"
START, END = "<!-- evalgate:numbers:start -->", "<!-- evalgate:numbers:end -->"


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


def render(readme: str) -> str:
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(readme):
        raise SystemExit(f"README.md sin marcadores {START} … {END}")
    return pattern.sub(f"{START}\n{table()}\n{END}", readme)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    current = README.read_text(encoding="utf-8")
    expected = render(current)
    if args.check:
        if current != expected:
            print(
                "R17 FALLA · la tabla de números del README no coincide con evals/reports/: `make report`",
                file=sys.stderr,
            )
            return 1
        print("R17 ok · README coincide con evals/reports/")
        return 0
    README.write_text(expected, encoding="utf-8")
    print("README.md regenerado desde evals/reports/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
