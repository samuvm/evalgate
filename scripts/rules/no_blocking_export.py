"""R1: ninguna traza puede tumbar ni ralentizar una petición. La parte que se ve en el código.

Por AST sobre `src/evalgate/proxy/`:

1. **Ningún import de exportadores.** Ni `evalgate.telemetry.exporters` (lo que dice RULES R1) ni los
   exportadores del SDK de OpenTelemetry (`opentelemetry.exporter*`, `opentelemetry.sdk.trace.export`). El
   proxy recibe un sumidero ya montado y lo llama; quién exporta y cómo no es asunto suyo. Si pudiera
   importar un exportador, un día alguien lo llamaría "solo aquí, que es rápido".
2. **Ningún `await` sobre `export()` ni `force_flush()`.** Esperar al almacén dentro de la petición es
   exactamente ralentizarla, y con ClickHouse caído, colgarla.

La otra mitad de R1 no se ve leyendo código y se mide: `make test-int -k degradation` tumba el contenedor
a mitad del test (contrato otel-genai §6).
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROXY = ROOT / "src" / "evalgate" / "proxy"
FORBIDDEN_IMPORTS = (
    "evalgate.telemetry.exporters",
    "opentelemetry.exporter",
    "opentelemetry.sdk.trace.export",
)
FORBIDDEN_AWAITS = {"export", "force_flush"}


def imported(node: ast.AST) -> list[str]:
    if isinstance(node, ast.Import):
        return [alias.name for alias in node.names]
    if isinstance(node, ast.ImportFrom) and node.module:
        return [node.module, *(f"{node.module}.{alias.name}" for alias in node.names)]
    return []


def awaited_name(node: ast.AST) -> str | None:
    if not (isinstance(node, ast.Await) and isinstance(node.value, ast.Call)):
        return None
    func = node.value.func
    if isinstance(func, ast.Attribute):
        return func.attr
    return func.id if isinstance(func, ast.Name) else None


problems: list[str] = []
files = sorted(PROXY.rglob("*.py"))
for path in files:
    where = path.relative_to(ROOT)
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        for name in imported(node):
            if name.startswith(FORBIDDEN_IMPORTS):
                problems.append(
                    f"{where}:{node.lineno} importa {name}: el proxy recibe un sumidero, no exporta"
                )
        if (awaited := awaited_name(node)) in FORBIDDEN_AWAITS:
            problems.append(
                f"{where}:{node.lineno} hace `await` sobre {awaited}(): la petición esperaría al almacén"
            )

for problem in sorted(set(problems)):
    print(f"R1 FALLA · {problem}", file=sys.stderr)
if not problems:
    print(f"R1 ok · {len(files)} módulos de proxy/ sin exportadores importados ni `await` sobre un export")
sys.exit(1 if problems else 0)
