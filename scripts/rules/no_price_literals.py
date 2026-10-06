"""R3: ningún precio vive en el código. Los precios están en `pricing/<YYYY-MM-DD>.yaml`.

Por AST sobre `src/evalgate/pricing/*.py`, falla ante:

1. cualquier literal `float`: un `0.0008` en este paquete solo puede ser un precio o un tipo de cambio;
2. `Decimal("…")` con una cadena literal, que es la forma educada de escribir lo mismo;
3. `Decimal(n)` con un entero literal distinto de 0 y de 1.

Lo que se admite, y por qué no es un agujero: los enteros sueltos (`1000` es la unidad del formato, "por 1k
tokens", y `2` son decimales de céntimo), y `Decimal(0)` / `Decimal(1)`, que son los neutros de la suma y de
la escala. Un precio de exactamente 0 o 1 escrito así pasaría, y por eso la regla no va sola: los tests de
`pricing/` inyectan siempre la tabla, y un `cost_of` que ignorara la tabla no pasaría ninguno.

Los tests quedan fuera a propósito: ahí los precios de ejemplo son el caso de prueba.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRICING = ROOT / "src" / "evalgate" / "pricing"
NEUTRAL = {0, 1}


def literal_price(node: ast.AST) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, float):
        return f"literal float {node.value!r}"
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "Decimal"):
        return None
    for arg in node.args:
        if not isinstance(arg, ast.Constant):
            continue
        if isinstance(arg.value, str):
            return f"Decimal({arg.value!r})"
        if isinstance(arg.value, int) and not isinstance(arg.value, bool) and arg.value not in NEUTRAL:
            return f"Decimal({arg.value!r})"
    return None


problems: list[str] = []
files = sorted(PRICING.rglob("*.py"))
for path in files:
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if found := literal_price(node):
            problems.append(f"{path.relative_to(ROOT)}:{getattr(node, 'lineno', '?')} {found}")

for problem in sorted(set(problems)):
    print(
        f"R3 FALLA · {problem}. Los precios viven en pricing/<fecha>.yaml, nunca en el código",
        file=sys.stderr,
    )
if not problems:
    print(f"R3 ok · {len(files)} módulos de pricing/ sin un solo precio literal")
sys.exit(1 if problems else 0)
