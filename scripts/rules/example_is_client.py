"""R13: examples/ never imports evalgate. The app is a client; adoption costs one environment variable."""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

violations: list[str] = []
for path in sorted((ROOT / "examples").rglob("*.py")):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        names: list[str] = []
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [node.module or ""]
        violations += [
            f"{path.relative_to(ROOT)}:{node.lineno} importa {n}"
            for n in names
            if n.split(".")[0] == "evalgate"
        ]

for violation in violations:
    print(f"R13 FALLA · {violation}", file=sys.stderr)
if not violations:
    print("R13 ok · examples/ no importa evalgate")
sys.exit(1 if violations else 0)
