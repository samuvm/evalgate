"""G-OPENAI-CONTRACT: every response the proxy returns validates against the pinned OpenAI OpenAPI
snapshot (docs/spec/openai-openapi-2.3.0.json), never against our own reading of it.

Measured set: every kind of response the proxy can emit, streaming frames included since F2.
"""

import json

import httpx
import pytest
from jsonschema import Draft202012Validator

from ._paths import ROOT
from ._proxy import Upstream, fixture, openai_validator, proxy, sse_events

CHAT = "/v1/chat/completions"
SSE = ROOT / "tests" / "fixtures" / "sse"
completion_errors = openai_validator("CreateChatCompletionResponse")
error_errors = openai_validator("ErrorResponse")
stream_errors = openai_validator("CreateChatCompletionStreamResponse")


def test_compliant_upstream_response_validates() -> None:
    response = proxy(Upstream(body=fixture("compliant_chat_completion.json"))).post(CHAT, content=b"{}")

    assert completion_errors(response.json()) == []


def test_ollama_response_validates_once_normalized() -> None:
    upstream = Upstream(body=fixture("ollama_chat_completion.json"))

    response = proxy(upstream, normalize=True).post(CHAT, content=fixture("ollama_request.json"))

    assert completion_errors(response.json()) == []


def test_raw_ollama_response_does_not_validate() -> None:
    """Why P-004 exists: Ollama 0.33.3 omits two required-but-nullable fields."""
    raw = json.loads(fixture("ollama_chat_completion.json"))

    assert sorted(completion_errors(raw)) == [
        "['choices', 0, 'message']: 'refusal' is a required property",
        "['choices', 0]: 'logprobs' is a required property",
    ]


@pytest.mark.parametrize(
    ("upstream", "request_body"),
    [
        (Upstream(error=httpx.ConnectError("refused")), b"{}"),
        (Upstream(error=httpx.ConnectError("refused")), b'{"model":"m","stream":true}'),
    ],
    ids=["502-upstream-down", "502-upstream-down-on-a-stream"],
)
def test_proxy_own_errors_validate_as_error_response(upstream: Upstream, request_body: bytes) -> None:
    response = proxy(upstream).post(CHAT, content=request_body)

    assert response.status_code >= 500
    assert error_errors(response.json()) == []


def test_every_frame_of_a_real_stream_validates() -> None:
    """La nota de G-OPENAI-CONTRACT dice "cuerpo JSON **y tramas SSE**". Transcripción real de Ollama."""
    transcript = (SSE / "13-reasoning-tokens.sse").read_bytes()
    upstream = Upstream(body=transcript, headers={"content-type": "text/event-stream"})

    response = proxy(upstream).post(CHAT, content=b'{"model":"m","stream":true}')

    events = sse_events(response.content)
    assert len(events) == 34, "sin tramas, un contrato en verde no demuestra nada"
    assert [error for event in events for error in stream_errors(event)] == []


def test_the_pinned_snapshot_contradicts_itself_and_this_is_where_it_is_written() -> None:
    """Por qué existe `honour_nullable` (ADR-011), como test y no como comentario.

    El snapshot se declara `openapi: 3.1.0` y usa `nullable: true`, que es palabra de 3.0 y ningún
    validador de JSON Schema respeta. Leído al pie de la letra rechaza el `"finish_reason": null` que manda
    el propio OpenAI en todas las tramas menos la última: no es el proveedor el que incumple el contrato,
    es el contrato el que se contradice.
    """
    chunk = sse_events((SSE / "13-reasoning-tokens.sse").read_bytes())[0]
    spec = json.loads((ROOT / "docs/spec/openai-openapi-2.3.0.json").read_text("utf-8"))
    literal = Draft202012Validator(
        {
            "$ref": "#/components/schemas/CreateChatCompletionStreamResponse",
            "components": spec["components"],
        }
    )

    assert [error.message for error in literal.iter_errors(chunk)][:1] == ["None is not of type 'string'"]
    assert stream_errors(chunk) == []
