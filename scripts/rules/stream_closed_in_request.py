"""R2 en el MONTAJE: el cuerpo de una respuesta en flujo se cierra dentro de la petición.

`finally_on_generators.py` vigila el módulo: todo generador de `proxy/streaming.py` emite el registro en un
`finally`. Eso es necesario y no basta. Entre el relevo y el cliente está la capa ASGI, que itera el cuerpo
con `async for` — y `async for` no cierra lo que recorre. Cuando el cliente cuelga, starlette cancela la
tarea con el generador suspendido en su `yield` y nadie lo cierra nunca: el `finally` existe, cumple la
letra de R2 y corre cuando el recolector quiere, fuera de la petición que pagó esos tokens (H-13 de
`docs/qa/hallazgos-F2.md`). Un `finally` que se dispara tarde no es contabilidad, es una promesa.

Por eso esta regla no mira `finally`, mira quién aprieta el gatillo. Dos comprobaciones sobre el AST de
`src/evalgate/proxy/`:

1. **Nadie monta un `StreamingResponse` pelado.** Construirlo es exactamente el defecto: hereda el
   `async for` que no cierra. Hay que pasar por una subclase de este paquete, que es la que se revisa.
2. **Toda subclase de `StreamingResponse` cierra su cuerpo en un `finally` de `__call__`.** En el `finally`
   y no en el camino feliz, porque el camino feliz es justo el que no cuelga; y en `__call__` porque es el
   único sitio que cubre las tres salidas de starlette (el cuerpo se agotó, el cliente colgó y la tarea fue
   cancelada, o la ruta de `spec_version >= 2.4` lanzó `ClientDisconnect`).

Probada en negativo antes de darla por buena, como las otras: quitando el `finally` de `AccountedStream` y
volviendo a `StreamingResponse(...)` en `streamed`, falla con el fichero y la línea.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "evalgate" / "proxy"
BASE = "StreamingResponse"


def named(node: ast.expr | None) -> str:
    """The trailing name of `X`, `a.X` or `a.b.X`; "" for anything that is not a name at all."""
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    return ""


def closes_its_body(klass: ast.ClassDef) -> bool:
    """True if `__call__` has a `try` whose `finally` calls `aclose()`."""
    for member in klass.body:
        if not isinstance(member, ast.AsyncFunctionDef) or member.name != "__call__":
            continue
        for block in ast.walk(member):
            if not isinstance(block, ast.Try):
                continue
            for statement in block.finalbody:
                for call in ast.walk(statement):
                    if isinstance(call, ast.Call) and named(call.func) == "aclose":
                        return True
    return False


problems: list[str] = []
if not PACKAGE.is_dir():
    print(f"R2 (montaje) ok · {PACKAGE.relative_to(ROOT)} aún no existe")
    sys.exit(0)

checked = 0
for path in sorted(PACKAGE.glob("*.py")):
    where = path.relative_to(ROOT)
    tree = ast.parse(path.read_text(encoding="utf-8"))

    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and any(named(base) == BASE for base in node.bases):
            checked += 1
            if not closes_its_body(node):
                problems.append(
                    f"{where}:{node.lineno} {node.name} hereda de {BASE} y no cierra su cuerpo con "
                    f"`aclose()` en un `finally` de `__call__`: el registro saldría cuando el recolector "
                    f"quiera, fuera de la petición"
                )
        elif isinstance(node, ast.Call) and named(node.func) == BASE:
            problems.append(
                f"{where}:{node.lineno} monta un {BASE} pelado: su `async for` no cierra el cuerpo cuando "
                f"el cliente cuelga. Usa una subclase de este paquete que lo cierre en `__call__`"
            )

for problem in problems:
    print(f"R2 (montaje) FALLA · {problem}", file=sys.stderr)
if not problems:
    print(f"R2 (montaje) ok · {checked} respuesta(s) en flujo cierran su cuerpo dentro de la petición")
sys.exit(1 if problems else 0)
