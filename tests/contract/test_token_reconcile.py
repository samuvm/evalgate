"""G-TOKENS-EXACT: lo que el proxy registra de una respuesta no-streaming es, exactamente, el bloque
`usage` que mandó el proveedor. Es aritmética, no estadística: la meta lleva `propuesta_admisible: false`.

El conjunto medido son respuestas **grabadas**: las dos sintéticas de F1 y tres respuestas reales de
Ollama 0.33.3 (`tests/fixtures/openai/recorded/`, con su procedencia). Se conducen por el proxy entero,
con el sumidero de uso enchufado, y se compara contra el cuerpo que entró.
"""

import json
from pathlib import Path

import pytest

from evalgate.proxy.streaming import SOURCE_ESTIMATED, SOURCE_PROVIDER, UsageRecord
from tests._meter import Meter

from ._paths import ROOT
from ._proxy import Upstream, proxy

CHAT = "/v1/chat/completions"
FIXTURES = ROOT / "tests" / "fixtures" / "openai"
RECORDED = [
    path
    for path in sorted(FIXTURES.rglob("*.json"))
    if json.loads(path.read_bytes()).get("object") == "chat.completion"
]


def through_the_proxy(body: bytes, *, normalize: bool = True) -> tuple[int, list[UsageRecord]]:
    records: list[UsageRecord] = []
    client = proxy(Upstream(body=body), normalize=normalize, on_usage=records.append)
    response = client.post(CHAT, content=b'{"model":"m"}')
    return response.status_code, records


@pytest.mark.parametrize("path", RECORDED, ids=lambda path: path.name)
def test_the_recorded_usage_is_what_gets_recorded(path: Path, meter: Meter) -> None:
    body = path.read_bytes()
    usage = json.loads(body)["usage"]

    status, records = through_the_proxy(body)

    counted = records[0].usage if len(records) == 1 else None
    ok = counted is not None and (counted.input_tokens, counted.output_tokens, counted.source) == (
        usage["prompt_tokens"],
        usage["completion_tokens"],
        SOURCE_PROVIDER,
    )
    meter.check("G-TOKENS-EXACT", ok)

    assert status == 200
    assert ok, f"{path.name}: registrado {counted}, el proveedor dijo {usage}"


def test_a_response_without_usage_is_recorded_as_an_estimate_and_says_so() -> None:
    """Nunca se inventa un número exacto: si el proveedor no lo dio, el registro lo declara estimado."""
    body = b'{"object":"chat.completion","choices":[{"message":{"content":"una dos tres"}}]}'

    _, records = through_the_proxy(body)

    assert records[0].usage.source == SOURCE_ESTIMATED
    assert records[0].usage.output_tokens == 3


def test_an_error_from_the_provider_is_not_accounted() -> None:
    """Un cuerpo de error no tiene tokens que contar, y un cero inventado sería contar mal."""
    body = b'{"error":{"message":"model not found","type":"api_error","param":null,"code":null}}'
    records: list[UsageRecord] = []

    proxy(Upstream(status=404, body=body), on_usage=records.append).post(CHAT, content=b"{}")

    assert records == []


def test_a_sink_that_blows_up_does_not_take_the_request_down() -> None:
    """R1: ninguna traza puede tumbar una petición. Ni siquiera la que escribe el propio usuario."""

    def explode(_: UsageRecord) -> None:
        raise RuntimeError("el exportador se ha caído")

    body = (FIXTURES / "compliant_chat_completion.json").read_bytes()
    response = proxy(Upstream(body=body), on_usage=explode).post(CHAT, content=b"{}")

    assert (response.status_code, response.content) == (200, body)
