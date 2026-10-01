"""PROJECT.md hito 0: the proxy is transparent. Byte-for-byte in both directions, errors included."""

import httpx
import pytest

from evalgate.proxy.translate import NORMALIZED_HEADER

from ._paths import ROOT
from ._proxy import Upstream, fixture, proxy

CHAT = "/v1/chat/completions"


@pytest.mark.parametrize("normalize", [False, True])
def test_compliant_response_is_byte_identical(normalize: bool) -> None:
    upstream = Upstream(body=fixture("compliant_chat_completion.json"))

    response = proxy(upstream, normalize=normalize).post(CHAT, content=fixture("ollama_request.json"))

    assert response.status_code == 200
    assert response.content == fixture("compliant_chat_completion.json")
    assert NORMALIZED_HEADER not in response.headers


def test_request_body_reaches_the_upstream_byte_identical() -> None:
    upstream = Upstream(body=fixture("compliant_chat_completion.json"))
    sent = b'{ "model": "m",\n  "messages": [ {"role": "user", "content": "\xc2\xbfacci\xc3\xb3n?"} ] }'

    proxy(upstream).post(CHAT, content=sent, headers={"content-type": "application/json"})

    assert upstream.received[0].content == sent
    assert str(upstream.received[0].url) == "http://upstream.test/v1/chat/completions"


def test_authorization_header_reaches_the_upstream() -> None:
    upstream = Upstream(body=fixture("compliant_chat_completion.json"))

    proxy(upstream).post(CHAT, content=b"{}", headers={"authorization": "Bearer sk-test"})

    assert upstream.received[0].headers["authorization"] == "Bearer sk-test"


def test_non_compliant_upstream_is_byte_identical_when_normalization_is_off() -> None:
    upstream = Upstream(body=fixture("ollama_chat_completion.json"))

    response = proxy(upstream, normalize=False).post(CHAT, content=fixture("ollama_request.json"))

    assert response.content == fixture("ollama_chat_completion.json")


def test_normalization_is_declared_in_a_header() -> None:
    upstream = Upstream(body=fixture("ollama_chat_completion.json"))

    response = proxy(upstream, normalize=True).post(CHAT, content=fixture("ollama_request.json"))

    assert response.headers[NORMALIZED_HEADER] == "choices.logprobs,choices.message.refusal"


@pytest.mark.parametrize("status", [400, 404, 429, 500])
def test_upstream_errors_pass_through_unchanged(status: int) -> None:
    body = b'{"error":{"message":"model \\"x\\" not found","type":"api_error","param":null,"code":null}}'
    upstream = Upstream(status=status, body=body)

    response = proxy(upstream, normalize=True).post(CHAT, content=b'{"model":"x"}')

    assert (response.status_code, response.content) == (status, body)


def test_unreachable_upstream_is_a_502_not_a_crash() -> None:
    upstream = Upstream(error=httpx.ConnectError("connection refused"))

    response = proxy(upstream).post(CHAT, content=fixture("ollama_request.json"))

    assert response.status_code == 502
    assert response.json()["error"]["type"] == "upstream_error"


def test_a_stream_reaches_the_client_byte_for_byte() -> None:
    """F2 sustituye al 501 de F1: `stream: true` ya no se rechaza, se reenvía y se contabiliza."""
    transcript = (ROOT / "tests" / "fixtures" / "sse" / "05-missing-usage-chunk.sse").read_bytes()
    upstream = Upstream(body=transcript, headers={"content-type": "text/event-stream"})

    response = proxy(upstream).post(CHAT, content=b'{"model":"m","stream":true}')

    assert (response.status_code, response.content) == (200, transcript)
    assert response.headers["content-type"] == "text/event-stream"
