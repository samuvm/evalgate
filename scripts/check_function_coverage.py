"""G-FUNC-COV: every public function of [tool.gate].testable has >= 1 unit-test context.

CONSTITUCION §2.6 and RULES.md §4.2:
1. A public function (no leading `_`, including public methods of public classes) is covered when at
   least one line of its body was executed inside a test context (`pytest --cov-context=test`).
2. Every public function of [tool.gate].property_obligatorio is also referenced by name from at least one
   file of tests/property/.
3. proxy/streaming.py is measured by corpus, not by function (scripts/rules/sse_corpus_coverage.py), so
   it is skipped here.

Usage: python scripts/check_function_coverage.py [--cov-json /tmp/cov.json]
Prints `funciones_sin_test=N` and exits 1 if N > 0.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path

from gatelib import ROOT, python_files, tool_gate

CORPUS_DRIVEN = {"src/evalgate/proxy/streaming.py"}


def public_functions(path: Path) -> list[tuple[str, int, int]]:
    """(qualified name, first body line, last line) of each public function or public method."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    found: list[tuple[str, int, int]] = []

    def visit(nodes: list[ast.stmt], prefix: str) -> None:
        for node in nodes:
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef) and not node.name.startswith("_"):
                found.append((prefix + node.name, node.body[0].lineno, node.end_lineno or node.lineno))
            elif isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                visit(node.body, f"{prefix}{node.name}.")

    visit(tree.body, "")
    return found


def tested_lines(cov_json: Path) -> dict[str, set[int]]:
    """Per file, the lines executed inside at least one test context."""
    report = json.loads(cov_json.read_text(encoding="utf-8"))
    lines: dict[str, set[int]] = {}
    for name, data in report["files"].items():
        contexts: dict[str, list[str]] = data.get("contexts", {})
        executed = {int(line) for line, ctxs in contexts.items() if any(ctx for ctx in ctxs)}
        lines[str((ROOT / name).resolve())] = executed
    return lines


def referenced_names(directory: Path) -> set[str]:
    names: set[str] = set()
    for path in directory.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Name):
                names.add(node.id)
            elif isinstance(node, ast.Attribute):
                names.add(node.attr)
            elif isinstance(node, ast.alias):
                names.add(node.name.split(".")[-1])
    return names


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cov-json", default="/tmp/cov.json")  # noqa: S108 - path fixed by GOALS.yaml G-FUNC-COV
    args = parser.parse_args()

    gate = tool_gate()
    executed = tested_lines(Path(args.cov_json))
    testable = [p for p in gate["testable"] if p not in CORPUS_DRIVEN]
    missing: list[str] = []
    for path in python_files(testable):
        lines = executed.get(str(path.resolve()), set())
        for name, first, last in public_functions(path):
            if not lines & set(range(first, last + 1)):
                missing.append(f"{path.relative_to(ROOT)}::{name} · sin test unitario")

    property_names = referenced_names(ROOT / "tests/property")
    for path in python_files(gate.get("property_obligatorio", [])):
        for name, _, _ in public_functions(path):
            if name.split(".")[-1] not in property_names:
                missing.append(f"{path.relative_to(ROOT)}::{name} · sin test de propiedad")

    for line in missing:
        print(f"G-FUNC-COV · {line}", file=sys.stderr)
    print(f"funciones_sin_test={len(missing)}")
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
