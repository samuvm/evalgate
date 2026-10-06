"""R4: una tabla de precios publicada es inmutable. Corregir un precio es publicar otro fichero.

`pricing/TABLES.lock` guarda el sha256 de cada `pricing/<YYYY-MM-DD>.yaml` publicado, con el mismo formato que
`thresholds.lock` y que `shasum -a 256`. Solo se regenera en un paso humano de publicación (RULES §7): una
tabla nueva se escribe y espera; publicar una tabla es sellarla en TABLES.lock. Falla si:

- una tabla del lock ha cambiado (alguien editó el pasado);
- una tabla del lock ya no está (alguien borró el pasado);
- hay una tabla sin sellar (escrita, pero todavía no publicada: no puede usarse para calcular nada).

Sin tablas y sin lock no hay nada que vigilar, y lo dice.
"""

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PRICING = ROOT / "pricing"
LOCK = PRICING / "TABLES.lock"


def sealed() -> dict[str, str]:
    if not LOCK.exists():
        return {}
    entries: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            entries[name.strip()] = digest
    return entries


lock = sealed()
tables = {
    str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted(PRICING.glob("*.yaml"))
}
problems = [
    f"{name} cambió tras publicarse (lock {lock[name][:12]}…, disco {digest[:12]}…)"
    for name, digest in tables.items()
    if name in lock and lock[name] != digest
]
problems += [f"{name} está en TABLES.lock y ya no existe" for name in lock if name not in tables]
problems += [
    f"{name} no está sellada en TABLES.lock: publicarla es sellarla" for name in tables if name not in lock
]

for problem in problems:
    print(f"R4 FALLA · {problem}", file=sys.stderr)
if not problems:
    print(f"R4 ok · {len(tables)} tabla(s) de precios, todas selladas y sin cambios")
sys.exit(1 if problems else 0)
