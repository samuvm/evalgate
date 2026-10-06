"""R8: el bootstrap es pareado o falla. No existe una función de bootstrap no pareado en el repositorio.

Por AST sobre todo `src/evalgate/`: la única función cuyo nombre contiene "bootstrap" es
`stats.paired_bootstrap.paired_bootstrap`, y ningún nombre de función sugiere un remuestreo independiente
(`unpaired`, `independent`, `two_sample`). Es una regla de nombres, y por eso no va sola: el test
`tests/unit/stats/test_paired_only.py` comprueba el comportamiento (casos distintos lanzan excepción; una
regresión uniforme se ve pareada y quedaría enterrada sin parear).
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "evalgate"
ALLOWED = ("src/evalgate/stats/paired_bootstrap.py", "paired_bootstrap")
SUSPECT = ("unpaired", "independent", "two_sample")

problems: list[str] = []
found = 0
for path in sorted(PACKAGE.rglob("*.py")):
    where = str(path.relative_to(ROOT))
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
            continue
        name = node.name.lower()
        if "bootstrap" in name:
            found += 1
            if (where, node.name) != ALLOWED:
                problems.append(
                    f"{where}:{node.lineno} define `{node.name}`: el único bootstrap es el pareado"
                )
        if any(word in name for word in SUSPECT):
            problems.append(f"{where}:{node.lineno} `{node.name}` sugiere un remuestreo no pareado")
if found == 0:
    problems.append("no existe `paired_bootstrap`: la puerta se ha quedado sin estadística")

for problem in problems:
    print(f"R8 FALLA · {problem}", file=sys.stderr)
if not problems:
    print("R8 ok · un único bootstrap en src/, y es el pareado")
sys.exit(1 if problems else 0)
