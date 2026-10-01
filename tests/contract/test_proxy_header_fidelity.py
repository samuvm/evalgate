"""Hallazgos H-01…H-12 de la reserva (`docs/qa/hallazgos-F1.md`), reproducidos con tests propios.

What the proxy must not do on the way through: lose a repeated field, merge two into one line, keep a
per-hop field, drop the query string, duplicate what its own server writes, or let the upstream sign a
declaration in evalgate's name. RFC 9110 §5.3 and §7.6.1, RFC 6265 §3, and ADR-007.
"""

import pytest

from evalgate.proxy.translate import NORMALIZED_HEADER

from ._proxy import Upstream, fixture, proxy

CHAT = "/v1/chat/completions"
COMPLIANT = "compliant_chat_completion.json"
ERROR_BODY = b'{"error":{"message":"model \\"x\\" not found","type":"api_error","param":null,"code":null}}'


def test_the_query_string_of_the_client_reaches_the_upstream() -> None:
    """H-02: the pinned OpenAPI declares no query parameter here, so the proxy has no ground to drop one."""
    upstream = Upstream(body=fixture(COMPLIANT))

    proxy(upstream).post(f"{CHAT}?api-version=2024-08-01&trace=on", content=fixture("ollama_request.json"))

    assert str(upstream.received[0].url) == (
        "http://upstream.test/v1/chat/completions?api-version=2024-08-01&trace=on"
    )


def test_a_request_field_named_by_connection_is_not_forwarded() -> None:
    """H-03: hop-by-hop is the fixed list *plus* whatever `Connection` names (RFC 9110 §7.6.1)."""
    upstream = Upstream(body=fixture(COMPLIANT))

    proxy(upstream).post(
        CHAT, content=b"{}", headers={"connection": "keep-alive, X-Client-Hop", "x-client-hop": "pool-7"}
    )

    assert "x-client-hop" not in upstream.received[0].headers


def test_a_repeated_request_field_reaches_the_upstream_with_every_value() -> None:
    """H-04: two lines of one field are its list; keeping only the last one loses a value in silence."""
    upstream = Upstream(body=fixture(COMPLIANT))

    proxy(upstream).post(
        CHAT, content=b"{}", headers=[("x-evalgate-trace", "alpha"), ("x-evalgate-trace", "beta")]
    )

    sent = [value for name, value in upstream.received[0].headers.multi_items() if name == "x-evalgate-trace"]
    assert sent == ["alpha", "beta"]


def test_a_response_field_named_by_connection_does_not_reach_the_client() -> None:
    """H-05: the upstream's per-hop state (its load balancer's) dies at this hop."""
    upstream = Upstream(
        body=fixture(COMPLIANT),
        headers={"content-type": "application/json", "connection": "X-Hop", "x-hop": "lb-3"},
    )

    response = proxy(upstream).post(CHAT, content=b"{}")

    assert "x-hop" not in response.headers


def test_two_set_cookie_lines_reach_the_client_as_two_lines() -> None:
    """H-06: joining them with a comma corrupts the cookie, because `expires` already has one."""
    cookies = [
        ("set-cookie", "__cf_bm=abc; expires=Mon, 01-Jan-2027 00:00:00 GMT; path=/"),
        ("set-cookie", "_cfuvid=xyz; path=/"),
    ]
    upstream = Upstream(body=fixture(COMPLIANT), headers=[("content-type", "application/json"), *cookies])

    response = proxy(upstream).post(CHAT, content=b"{}")

    assert response.headers.get_list("set-cookie") == [value for _, value in cookies]


def test_the_date_and_server_of_the_upstream_are_not_forwarded() -> None:
    """H-01: uvicorn writes its own `Date` and `Server`; forwarding these gives the client two lines of each.

    The duplication itself is only visible with a served process (the in-memory client has no HTTP server
    that adds them), so what is pinned here is its cause: they never leave the proxy.
    """
    upstream = Upstream(
        body=fixture(COMPLIANT),
        headers={
            "content-type": "application/json",
            "date": "Mon, 01 Jan 2027 00:00:00 GMT",
            "server": "cloudflare",
        },
    )

    response = proxy(upstream).post(CHAT, content=b"{}")

    assert [name for name in ("date", "server") if name in response.headers] == []


@pytest.mark.parametrize("normalize", [False, True])
@pytest.mark.parametrize("status", [200, 400, 500])
def test_the_upstream_cannot_sign_a_normalization_in_evalgates_name(status: int, normalize: bool) -> None:
    """H-07…H-12, ADR-007: that header means *the proxy touched this body*. Here it did not touch it."""
    body = fixture(COMPLIANT) if status == 200 else ERROR_BODY
    upstream = Upstream(
        status=status,
        body=body,
        headers={
            "content-type": "application/json",
            NORMALIZED_HEADER: "choices.logprobs,choices.message.refusal",
        },
    )

    response = proxy(upstream, normalize=normalize).post(CHAT, content=fixture("ollama_request.json"))

    assert (response.content, NORMALIZED_HEADER in response.headers) == (body, False)
