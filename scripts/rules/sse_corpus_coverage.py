"""RULES §4.2 punto 3: `proxy/streaming.py` no se mide por función, se mide por corpus.

Falla si uno de los 12 casos límite de `REQUIRED` no tiene fixture, si un fixture no está declarado, o si
un fixture no lo consume ningún test. La lista vive aquí, no en el manifiesto: `tests/fixtures/sse/CASES.yaml`
solo dice qué fichero cubre cada caso, y el texto tiene que coincidir letra a letra. Así, renombrar un caso
para que encaje con un fixture que hace otra cosa exige tocar también esta regla, y se ve en la revisión.

Los 12 son un SUELO. El corpus puede crecer con lo que hagan los proveedores de verdad: esos van
en `extra:` del manifiesto, con su motivo escrito, y se les exige lo mismo —que algún test los consuma—.

`tests/holdout/` queda fuera del escaneo a propósito: es la suite reservada, privada, y un fixture que solo
consumiera ella no sería cobertura de los tests públicos.
"""

import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "sse"
MANIFEST = CORPUS / "CASES.yaml"
REQUIRED = [
    "corte de cliente",
    "corte de proveedor",
    "chunk malformado",
    "timeout a mitad",
    "chunk final de `usage` ausente",
    "`[DONE]` sin `usage`",
    "unicode partido entre chunks",
    "keep-alive vacío",
    "error a mitad del stream",
    "doble `[DONE]`",
    "chunk con `finish_reason` inesperado",
    "stream de longitud 0",
]


def consumers() -> str:
    """Every public test source, concatenated. A fixture is covered if its name is in here."""
    tests = (path for path in (ROOT / "tests").rglob("*.py") if "holdout" not in path.parts)
    return "\n".join(path.read_text(encoding="utf-8") for path in tests)


manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
cases = REQUIRED
declared: list[dict[str, str]] = manifest["casos"]
extra: list[dict[str, str]] = manifest.get("extra") or []
present = {path.name for path in CORPUS.glob("*.sse")}
sources = consumers()

problems: list[str] = []
if [entry["caso"] for entry in declared] != cases:
    problems.append(
        f"CASES.yaml no declara los 12 casos obligatorios en orden.\n"
        f"  obligatorios: {cases}\n  CASES.yaml  : {[entry['caso'] for entry in declared]}"
    )

for entry in declared + extra:
    fixture = entry["fixture"]
    label = f"caso «{entry['caso']}»" if "caso" in entry else f"extra {fixture}"
    if fixture not in present:
        problems.append(f"{label} declara {fixture} y ese fichero no existe")
    elif fixture not in sources:
        problems.append(f"{fixture} no lo consume ningún test: un fixture sin test no es cobertura")
    if "caso" not in entry and not entry.get("porque", "").strip():
        problems.append(f"{fixture} está declarado como extra y no dice por qué existe")

for orphan in sorted(present - {entry["fixture"] for entry in declared + extra}):
    problems.append(f"{orphan} está en el corpus y no lo declara CASES.yaml")

for problem in problems:
    print(f"CORPUS SSE FALLA · {problem}", file=sys.stderr)
if not problems:
    print(
        f"corpus SSE ok · {len(cases)} casos obligatorios + {len(extra)} extra declarados, "
        f"{len(present)} fixtures, todos consumidos"
    )
sys.exit(1 if problems else 0)
