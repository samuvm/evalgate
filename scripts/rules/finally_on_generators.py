"""R2: la contabilidad se cierra siempre.

Toda corrutina generadora de `proxy/streaming.py` emite el registro de uso en un `finally` y **sobrevive**
a `asyncio.CancelledError`: un cliente que cuelga a mitad de respuesta ya ha pagado los tokens que el
proveedor emitió, así que esos tokens se cuentan. Dos comprobaciones sobre el AST:

1. Todo generador asíncrono tiene un `try` con `finally`, y en ese `finally` se llama al callback que
   recibe por parámetro. Llamarlo en el camino feliz no vale: el camino feliz es justo el que no falla.
2. Ningún `except` que capture `CancelledError`, `GeneratorExit` o `BaseException` se los traga: tiene que
   volver a lanzarlos. Tragarse una cancelación convierte un corte de cliente en una corrutina zombi.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TARGET = ROOT / "src" / "evalgate" / "proxy" / "streaming.py"
MUST_RERAISE = {"CancelledError", "GeneratorExit", "BaseException"}


def caught(handler: ast.ExceptHandler) -> set[str]:
    kinds = handler.type.elts if isinstance(handler.type, ast.Tuple) else [handler.type]
    names = set()
    for kind in kinds:
        if isinstance(kind, ast.Name):
            names.add(kind.id)
        elif isinstance(kind, ast.Attribute):
            names.add(kind.attr)
    return names


problems: list[str] = []
if not TARGET.exists():
    print(f"R2 ok · {TARGET.relative_to(ROOT)} aún no existe (llega en F2)")
    sys.exit(0)

for function in ast.walk(ast.parse(TARGET.read_text(encoding="utf-8"))):
    if not isinstance(function, ast.AsyncFunctionDef):
        continue
    if not any(isinstance(node, ast.Yield | ast.YieldFrom) for node in ast.walk(function)):
        continue

    callbacks = {argument.arg for argument in function.args.args + function.args.kwonlyargs}
    emits = any(
        isinstance(call, ast.Call) and isinstance(call.func, ast.Name) and call.func.id in callbacks
        for block in ast.walk(function)
        if isinstance(block, ast.Try)
        for statement in block.finalbody
        for call in ast.walk(statement)
    )
    if not emits:
        problems.append(
            f"{function.name}:{function.lineno} es un generador asíncrono y no emite el registro de uso "
            f"en un `finally`"
        )

    for handler in (n for n in ast.walk(function) if isinstance(n, ast.ExceptHandler)):
        if caught(handler) & MUST_RERAISE and not any(
            isinstance(node, ast.Raise) for node in ast.walk(handler)
        ):
            problems.append(
                f"{function.name}:{handler.lineno} captura {sorted(caught(handler))} y no vuelve a lanzarla"
            )

for problem in problems:
    print(f"R2 FALLA · {problem}", file=sys.stderr)
if not problems:
    print("R2 ok · todo generador de proxy/streaming.py cierra la contabilidad en `finally`")
sys.exit(1 if problems else 0)
