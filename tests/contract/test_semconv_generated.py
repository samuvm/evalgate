"""`telemetry/semconv/` es GENERADO desde el modelo pineado, y estos tests son su contrato.

Tres afirmaciones distintas, y separarlas importa porque fallan por motivos distintos:

1. **El snapshot vendorizado es el que dice ser.** `docs/spec/otel-semconv.sha256` lo fija fichero a
   fichero y su cabecera declara el commit, que tiene que ser el `sha` de `otel-semconv.lock`. Sin esto,
   "generado desde el lock" es una frase.
2. **Lo generado es exactamente lo que el generador produce hoy.** Se comprueba invocando su `--check`, que
   vuelve a renderizar desde el snapshot y compara. Es lo que convierte "no se escribe a mano" en algo
   verificable en vez de en una convención que alguien romperá un martes.
3. **Los nombres obligatorios del contrato están**, con el valor literal que el contrato exige
   (`docs/CONTRACTS/otel-genai.md` §4). Un span al que le falte uno es un span roto.

Sin red (R15): el paso que descarga es `--fetch`, y no se ejecuta aquí.
"""

import hashlib
import re
import subprocess
import sys

from evalgate.telemetry import semconv

from ._paths import ROOT

SNAPSHOT = ROOT / "docs" / "spec" / "otel-semconv"
MANIFEST = ROOT / "docs" / "spec" / "otel-semconv.sha256"

# Literal de docs/CONTRACTS/otel-genai.md §4. Se escribe aquí a propósito: si el contrato cambia, este
# test tiene que fallar y obligar a mirarlo, no adaptarse solo leyendo el mismo sitio que el generador.
SPAN_OBLIGATORIOS = {
    "OPERATION_NAME": "gen_ai.operation.name",
    "PROVIDER_NAME": "gen_ai.provider.name",
    "REQUEST_MODEL": "gen_ai.request.model",
    "RESPONSE_MODEL": "gen_ai.response.model",
    "USAGE_INPUT_TOKENS": "gen_ai.usage.input_tokens",
    "USAGE_OUTPUT_TOKENS": "gen_ai.usage.output_tokens",
    "REQUEST_TEMPERATURE": "gen_ai.request.temperature",
    "REQUEST_MAX_TOKENS": "gen_ai.request.max_tokens",
    "RESPONSE_FINISH_REASONS": "gen_ai.response.finish_reasons",
    "ERROR_TYPE": "error.type",
    "SERVER_ADDRESS": "server.address",
}
METRICAS_OBLIGATORIAS = {
    "TOKEN_USAGE": "gen_ai.client.token.usage",
    "OPERATION_DURATION": "gen_ai.client.operation.duration",
}


def _lock(path: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            key, value = line.split(":", maxsplit=1)
            fields[key.strip()] = value.strip()
    return fields


def _manifest() -> dict[str, str]:
    entries: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            entries[name.strip()] = digest
    return entries


def test_the_vendored_snapshot_matches_its_manifest() -> None:
    """Byte a byte. Un YAML editado a mano aquí falsificaría todo lo que se genere debajo."""
    entries = _manifest()
    found = {str(p.relative_to(SNAPSHOT)) for p in SNAPSHOT.rglob("*.yaml")}

    assert found == set(entries), f"snapshot y manifiesto no cuadran: {found ^ set(entries)}"
    for name, digest in entries.items():
        assert hashlib.sha256((SNAPSHOT / name).read_bytes()).hexdigest() == digest, name


def test_the_snapshot_comes_from_the_commit_the_lock_pins() -> None:
    """El snapshot no vale por sí mismo: vale porque es el commit que `otel-semconv.lock` fija."""
    declared = re.search(r"^# commit: ([0-9a-f]{40})", MANIFEST.read_text(encoding="utf-8"), re.M)

    assert declared is not None, "la cabecera del manifiesto no declara el commit"
    assert declared.group(1) == _lock("otel-semconv.lock")["sha"]


def test_the_generated_module_is_exactly_what_the_generator_writes() -> None:
    """R5 y el mapa: `telemetry/semconv/` no se escribe a mano. `--check` lo vuelve a renderizar."""
    done = subprocess.run(  # noqa: S603 · ruta fija dentro del repo, sin entrada del usuario
        [sys.executable, str(ROOT / "scripts" / "gen_semconv.py"), "--check"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    )

    assert done.returncode == 0, f"lo generado no coincide con el generador:\n{done.stdout}{done.stderr}"


def test_every_mandatory_span_attribute_is_published_with_its_literal_name() -> None:
    """Contrato otel-genai §4, lista literal."""
    for name, value in SPAN_OBLIGATORIOS.items():
        assert getattr(semconv, name, None) == value, f"{name} deberia valer {value!r}"


def test_every_mandatory_metric_is_published_with_its_literal_name() -> None:
    """Las dos métricas `gen_ai.*` del contrato §4. `app.spans.dropped` es nuestra y no sale de aquí."""
    for name, value in METRICAS_OBLIGATORIAS.items():
        assert getattr(semconv, name, None) == value, f"{name} deberia valer {value!r}"


def test_the_generated_module_declares_where_it_came_from() -> None:
    """Un fichero generado que no dice de dónde sale es un fichero escrito a mano con suerte."""
    pinned = _lock("otel-semconv.lock")

    assert pinned["sha"] == semconv.SEMCONV_COMMIT
    assert pinned["version"] == semconv.SEMCONV_VERSION
