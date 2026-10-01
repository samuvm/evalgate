"""Genera `src/evalgate/telemetry/semconv/` desde el modelo pineado en `otel-semconv.lock`.

El contrato `docs/CONTRACTS/otel-genai.md` §2 exige modelo interno propio y una **capa de traducción**: los
nombres `gen_ai.*` no se escriben a mano en ninguna parte del código, salen de aquí. Y R5 lo cierra: ese es
el único paquete donde puede aparecer un literal `gen_ai.*`.

Tres modos, y la separación es deliberada:

* `--fetch`   descarga el tarball del commit que fija el lock y revendoriza `docs/spec/otel-semconv/` con su
              manifiesto. **Es el único paso que usa red**, y no lo ejecuta ningún test (R15).
* (sin flags) renderiza el paquete desde el snapshot vendorizado. Offline y determinista.
* `--check`   renderiza en memoria y compara con lo que hay en disco. Es lo que convierte "generado, no se
              escribe a mano" en algo que el gate verifica en vez de en una costumbre.

Qué se rinde y qué no: los atributos NO obsoletos de `model/gen-ai/registry.yaml`, más `error.type` y
`server.address`, que el contrato §4 exige en el span y viven fuera del árbol gen-ai; y las métricas de
`model/gen-ai/metrics.yaml`. Los ficheros bajo `deprecated/` se vendorizan (son parte de la ruta pineada)
y no se rinden: publicar una constante obsoleta es invitar a usarla.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import sys
import tarfile
import urllib.request
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "otel-semconv.lock"
SNAPSHOT = ROOT / "docs" / "spec" / "otel-semconv"
MANIFEST = ROOT / "docs" / "spec" / "otel-semconv.sha256"
TARGET = ROOT / "src" / "evalgate" / "telemetry" / "semconv" / "__init__.py"
TREES = ("model/gen-ai", "model/error", "model/server")
# Sólo estos dos salen de fuera del árbol gen-ai, y salen porque el contrato §4 los exige en el span.
FOREIGN = ("error.type", "server.address")


def lock() -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            key, value = line.split(":", maxsplit=1)
            fields[key.strip()] = value.strip()
    return fields


def constant(identifier: str) -> str:
    """`gen_ai.usage.input_tokens` -> `USAGE_INPUT_TOKENS`; `error.type` -> `ERROR_TYPE`.

    Se quita el prefijo del espacio de nombres propio de GenAI porque repetirlo en cada constante no añade
    nada dentro de un módulo que se llama `semconv`; lo de fuera conserva su id entero, que es lo que lo
    distingue.
    """
    for prefix in ("gen_ai.client.", "gen_ai."):
        if identifier.startswith(prefix):
            return identifier[len(prefix) :].replace(".", "_").upper()
    return identifier.replace(".", "_").upper()


def groups(path: Path) -> list[dict[str, Any]]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return list(loaded.get("groups") or [])


def attributes(tree: str, keep: tuple[str, ...] | None = None) -> dict[str, str]:
    """Atributos vivos del árbol, como `{id: tipo}`. `keep` limita a una lista concreta."""
    found: dict[str, str] = {}
    for path in sorted((SNAPSHOT / tree).glob("*.yaml")):  # sin `rglob`: deja fuera `deprecated/`
        for group in groups(path):
            for attribute in group.get("attributes") or []:
                identifier = attribute.get("id")
                if not identifier or "deprecated" in attribute:
                    continue
                if keep is not None and identifier not in keep:
                    continue
                kind = attribute.get("type")
                found[identifier] = "enum" if isinstance(kind, dict) else str(kind)
    return found


def metrics() -> dict[str, str]:
    found: dict[str, str] = {}
    for path in sorted((SNAPSHOT / "model/gen-ai").glob("*.yaml")):
        for group in groups(path):
            name = group.get("metric_name")
            if group.get("type") == "metric" and name and "deprecated" not in group:
                found[str(name)] = str(group.get("unit", ""))
    return found


def render() -> str:
    pinned = lock()
    attrs = attributes("model/gen-ai")
    for tree in ("model/error", "model/server"):
        attrs.update(attributes(tree, keep=FOREIGN))
    found = metrics()

    names: dict[str, str] = {}
    for identifier in [*sorted(attrs), *sorted(found)]:
        name = constant(identifier)
        if name in names:
            raise SystemExit(f"colisión de constantes: {identifier} y {names[name]} -> {name}")
        names[name] = identifier

    out = io.StringIO()
    out.write('"""GENERADO por `scripts/gen_semconv.py`. NO SE EDITA A MANO.\n\n')
    out.write("Nombres externos de OpenTelemetry, renderizados desde el snapshot vendorizado del commit\n")
    out.write("que fija `otel-semconv.lock`. El modelo interno no usa ninguno de estos nombres: el\n")
    out.write("traductor es el único módulo que los conoce (contrato otel-genai §2), y R5 impide que un\n")
    out.write("literal `gen_ai.*` aparezca fuera de aquí.\n\n")
    out.write("Subir la versión es un cambio consciente: entrada en CHANGELOG y revisión del traductor.\n")
    out.write('"""\n\n')
    out.write(f'SEMCONV_REPO = "{pinned["repo"]}"\n')
    out.write(f'SEMCONV_VERSION = "{pinned["version"]}"\n')
    out.write(f'SEMCONV_COMMIT = "{pinned["sha"]}"\n\n')

    out.write("# --- Atributos ---\n")
    for identifier in sorted(attrs):
        out.write(f'{constant(identifier)} = "{identifier}"\n')
    out.write("\n# --- Métricas ---\n")
    for identifier in sorted(found):
        out.write(f'{constant(identifier)} = "{identifier}"\n')

    out.write("\n# Tipo declarado por el modelo, para que el traductor pueda validar lo que emite.\n")
    out.write("ATTRIBUTE_TYPES: dict[str, str] = {\n")
    for identifier in sorted(attrs):
        out.write(f'    "{identifier}": "{attrs[identifier]}",\n')
    out.write("}\n\n")
    out.write("METRIC_UNITS: dict[str, str] = {\n")
    for identifier in sorted(found):
        out.write(f'    "{identifier}": "{found[identifier]}",\n')
    out.write("}\n")
    return out.getvalue()


def fetch() -> int:
    """El único paso con red. Revendoriza el snapshot y reescribe su manifiesto."""
    pinned = lock()
    url = f"https://codeload.github.com/{pinned['repo']}/tar.gz/{pinned['sha']}"
    with urllib.request.urlopen(url, timeout=120) as response:
        blob = response.read()
    prefix = f"{pinned['repo'].split('/')[-1]}-{pinned['sha']}/"

    for path in sorted(SNAPSHOT.rglob("*.yaml")):
        path.unlink()
    with tarfile.open(fileobj=io.BytesIO(blob)) as archive:
        for member in archive.getmembers():
            name = member.name.removeprefix(prefix)
            if not member.isfile() or not any(name.startswith(t + "/") for t in TREES):
                continue
            source = archive.extractfile(member)
            if source is None:
                continue
            out = SNAPSHOT / name
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(source.read())

    header = MANIFEST.read_text(encoding="utf-8").split("\n")
    kept = [line for line in header if line.startswith("#")]
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  {p.relative_to(SNAPSHOT)}"
        for p in sorted(SNAPSHOT.rglob("*.yaml"))
    ]
    MANIFEST.write_text("\n".join([*kept, *lines]) + "\n", encoding="utf-8")
    print(f"snapshot revendorizado desde {pinned['sha'][:12]}… · {len(lines)} ficheros")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fetch", action="store_true", help="descarga el modelo pineado (usa red)")
    parser.add_argument("--check", action="store_true", help="falla si lo generado no está al día")
    args = parser.parse_args()

    if args.fetch:
        return fetch()

    expected = render()
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.is_file() else ""
        if current != expected:
            print(
                f"SEMCONV FALLA · {TARGET.relative_to(ROOT)} no es lo que el generador produce desde "
                f"{SNAPSHOT.relative_to(ROOT)}. Regenera con `python scripts/gen_semconv.py`.",
                file=sys.stderr,
            )
            return 1
        print(f"semconv ok · {TARGET.relative_to(ROOT)} al día con el commit del lock")
        return 0

    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(expected, encoding="utf-8")
    print(f"generado {TARGET.relative_to(ROOT)} desde {SNAPSHOT.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
