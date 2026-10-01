"""RULES §4.2 punto 3: `proxy/streaming.py` no se mide por función, se mide por corpus.

Falla si un caso límite de `docs/PLAN.md` §3 no tiene fixture, si un fixture no está declarado, o si un
fixture no lo consume ningún test. Los 12 casos se leen de PLAN.md, que es de solo lectura: el manifiesto
`tests/fixtures/sse/CASES.yaml` solo dice qué fichero cubre cada uno, y el texto tiene que coincidir letra
a letra. Así, renombrar un caso para que encaje con un fixture que hace otra cosa no pasa desapercibido.

Los 12 de PLAN son un SUELO. El corpus puede crecer con lo que hagan los proveedores de verdad: esos van
en `extra:` del manifiesto, con su motivo escrito, y se les exige lo mismo —que algún test los consuma—.

`tests/holdout/` queda fuera del escaneo a propósito: es ilegible para el constructor (CONSTITUCION §2.5
nº 4) y un fixture que solo consumiera la reserva no sería cobertura suya.
"""

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CORPUS = ROOT / "tests" / "fixtures" / "sse"
MANIFEST = CORPUS / "CASES.yaml"
PLAN = ROOT / "docs" / "PLAN.md"


def plan_cases() -> list[str]:
    """The 12 names, in order, as `PLAN.md` §3 writes them."""
    section = re.split(r"^## ", PLAN.read_text(encoding="utf-8"), flags=re.M)
    third = next(part for part in section if part.startswith("3."))
    listed = third.split("---")[0].rsplit(":", 1)[-1]
    return [re.sub(r"\s+", " ", case).strip().rstrip(".") for case in listed.split("·") if case.strip()]


def consumers() -> str:
    """Every test source the builder may read, concatenated. A fixture is covered if its name is in here."""
    tests = (path for path in (ROOT / "tests").rglob("*.py") if "holdout" not in path.parts)
    return "\n".join(path.read_text(encoding="utf-8") for path in tests)


manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
cases = plan_cases()
declared: list[dict[str, str]] = manifest["casos"]
extra: list[dict[str, str]] = manifest.get("extra") or []
present = {path.name for path in CORPUS.glob("*.sse")}
sources = consumers()

problems: list[str] = []
if [entry["caso"] for entry in declared] != cases:
    problems.append(
        f"CASES.yaml no declara los casos de PLAN.md §3 en orden.\n"
        f"  PLAN.md  : {cases}\n  CASES.yaml: {[entry['caso'] for entry in declared]}"
    )
if len(cases) != 12:
    problems.append(f"PLAN.md §3 enumera {len(cases)} casos, no 12: la lista o el parseo han cambiado")

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
        f"corpus SSE ok · {len(cases)} casos de PLAN.md §3 + {len(extra)} extra declarados, "
        f"{len(present)} fixtures, todos consumidos"
    )
sys.exit(1 if problems else 0)
