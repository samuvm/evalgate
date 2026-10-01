"""Anti-gaming #1 (CONSTITUCION §2.5): per test file, n_tests, n_asserts and sha256.

`python scripts/test_inventory.py` prints the current inventory as JSON.
`python scripts/test_inventory.py --against <inventory.json>` fails if any file lost tests or asserts
(a missing file counts as zero). tests/holdout/ is excluded: the builder never reads it.
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import json
import sys
from pathlib import Path

from gatelib import ROOT

EXCLUDED = ROOT / "tests" / "holdout"


def count(path: Path) -> dict[str, int | str]:
    source = path.read_bytes()
    tests = asserts = 0
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and node.name.startswith("test"):
            tests += 1
        elif isinstance(node, ast.Assert) or (
            isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "raises"
        ):
            asserts += 1
    return {"n_tests": tests, "n_asserts": asserts, "sha": hashlib.sha256(source).hexdigest()}


def inventory() -> dict[str, dict[str, int | str]]:
    files = sorted(p for p in (ROOT / "tests").rglob("test_*.py") if EXCLUDED not in p.parents)
    return {str(p.relative_to(ROOT)): count(p) for p in files}


def regressions(
    current: dict[str, dict[str, int | str]], previous: dict[str, dict[str, int | str]]
) -> list[str]:
    found: list[str] = []
    for name, before in previous.items():
        now = current.get(name, {"n_tests": 0, "n_asserts": 0})
        for key in ("n_tests", "n_asserts"):
            if int(now[key]) < int(before[key]):
                found.append(f"{name}: {key} {before[key]} -> {now[key]}")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--against", type=Path)
    args = parser.parse_args()
    current = inventory()
    if args.against is None:
        print(json.dumps(current, indent=2, sort_keys=True))
        return 0
    if not args.against.is_file():
        print(f"inventario: sin referencia previa ({args.against}); nada que comparar")
        return 0
    lost = regressions(current, json.loads(args.against.read_text(encoding="utf-8")))
    for line in lost:
        print(f"ANTI-GAMING · tests o asserts perdidos · {line}", file=sys.stderr)
    total = sum(int(v["n_tests"]) for v in current.values())
    print(f"inventario: {len(current)} ficheros, {total} tests, regresiones={len(lost)}")
    return 1 if lost else 0


if __name__ == "__main__":
    sys.exit(main())
