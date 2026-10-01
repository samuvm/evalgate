"""R5: ningún literal `gen_ai.*` fuera de `src/evalgate/telemetry/semconv/`.

El contrato `docs/CONTRACTS/otel-genai.md` §2 no pide usar los nombres de OpenTelemetry: pide **no atarse
a ellos**. El modelo interno es propio y estable, y un único módulo —generado desde el commit pineado—
conoce los nombres externos. Si un `"gen_ai.usage.input_tokens"` se cuela en el exportador, en el proxy o
en un panel, la traducción deja de ser una capa y pasa a ser una costumbre: subir la versión del pin ya no
es revisar un fichero, es buscar por todo el repo.

Se mira el AST y no el texto: un `gen_ai.` dentro de un comentario o de una cadena de documentación es
prosa y puede explicar precisamente esto. Lo que se prohíbe es el literal que acaba ejecutándose.

Los tests quedan fuera a propósito: un test de contrato tiene que poder escribir el nombre externo a mano,
porque si lo importara del mismo módulo que valida no estaría comprobando nada.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / "src" / "evalgate"
ALLOWED = PACKAGE / "telemetry" / "semconv"
PREFIX = "gen_ai."

problems: list[str] = []
checked = 0
for path in sorted(PACKAGE.rglob("*.py")):
    if ALLOWED in path.parents:
        continue
    checked += 1
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and node.value.startswith(PREFIX):
            problems.append(
                f"{path.relative_to(ROOT)}:{node.lineno} literal {node.value!r}. Los nombres externos "
                f"salen de evalgate.telemetry.semconv, que se genera desde otel-semconv.lock"
            )

for problem in problems:
    print(f"R5 FALLA · {problem}", file=sys.stderr)
if not problems:
    print(f"R5 ok · {checked} módulos sin literales `gen_ai.*` fuera de telemetry/semconv/")
sys.exit(1 if problems else 0)
