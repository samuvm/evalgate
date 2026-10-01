import json

import pytest

from evalgate.proxy.streaming import (
    END_CLIENT_DISCONNECT,
    END_DONE,
    END_ERROR,
    END_TIMEOUT,
    END_UPSTREAM_EOF,
    SOURCE_ESTIMATED,
    SOURCE_PROVIDER,
    Usage,
    UsageRecord,
)
from evalgate.proxy.translate import (
    NORMALIZED_HEADER,
    CallOrigin,
    RequestFacts,
    forward_request_headers,
    forward_response_headers,
    is_stream_request,
    llm_call,
    normalize_chat_completion,
    record_of_completion,
    request_facts,
    upstream_url,
)
from evalgate.telemetry.model import LlmCall

OLLAMA_RESPONSE = (
    b'{"id":"chatcmpl-557","object":"chat.completion","created":1789045001,"model":"qwen3.5:4b-mlx",'
    b'"system_fingerprint":"fp_ollama","choices":[{"index":0,"message":{"role":"assistant",'
    b'"content":"\xc2\xa1Hola!"},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":15,"completion_tokens":4,"total_tokens":19}}'
)
COMPLIANT_RESPONSE = (
    b'{ "id": "chatcmpl-1", "object": "chat.completion", "created": 1, "model": "m",\n'
    b'  "choices": [ { "index": 0, "logprobs": null, "finish_reason": "stop",\n'
    b'    "message": { "role": "assistant", "content": "ok", "refusal": null } } ] }'
)


@pytest.mark.parametrize(
    ("base", "path"),
    [
        ("http://localhost:11434/v1", "chat/completions"),
        ("http://localhost:11434/v1/", "/chat/completions"),
        ("http://localhost:11434/v1/", "chat/completions"),
    ],
)
def test_upstream_url_joins_with_exactly_one_slash(base: str, path: str) -> None:
    assert upstream_url(base, path) == "http://localhost:11434/v1/chat/completions"


def test_request_headers_drop_hop_by_hop_and_encoding_but_keep_auth() -> None:
    headers = [
        ("Host", "proxy:8080"),
        ("Content-Length", "12"),
        ("Connection", "keep-alive"),
        ("Accept-Encoding", "gzip"),
        ("Authorization", "Bearer x"),
        ("Content-Type", "application/json"),
    ]

    assert forward_request_headers(headers) == [
        ("Authorization", "Bearer x"),
        ("Content-Type", "application/json"),
    ]


def test_response_headers_drop_content_encoding_and_length() -> None:
    headers = [
        ("content-encoding", "gzip"),
        ("content-length", "99"),
        ("transfer-encoding", "chunked"),
        ("content-type", "application/json"),
        ("x-request-id", "abc"),
    ]

    assert forward_response_headers(headers) == [
        ("content-type", "application/json"),
        ("x-request-id", "abc"),
    ]


def test_repeated_request_field_keeps_every_value_and_its_order() -> None:
    """H-04: two lines of one field are its list, and their order is part of the meaning. RFC 9110 §5.3."""
    headers = [("x-trace", "alpha"), ("content-type", "application/json"), ("x-trace", "beta")]

    assert forward_request_headers(headers) == headers


def test_repeated_response_field_is_not_merged_into_one_line() -> None:
    """H-06: `Set-Cookie` cannot be joined with commas: the `expires` date already has one. RFC 6265 §3."""
    cookies = [("set-cookie", "__cf_bm=a; expires=Mon, 01-Jan-2027 00:00 GMT"), ("set-cookie", "_cfuvid=b")]

    assert forward_response_headers(cookies) == cookies


@pytest.mark.parametrize(
    "connection", ["X-Client-Hop", "keep-alive, X-Client-Hop", "keep-alive,x-client-hop"]
)
def test_request_fields_named_by_connection_are_hop_by_hop(connection: str) -> None:
    """H-03: RFC 9110 §7.6.1. The fixed list is not the rule: `Connection` names more, case-insensitively."""
    headers = [("connection", connection), ("X-Client-Hop", "pool-7"), ("authorization", "Bearer x")]

    assert forward_request_headers(headers) == [("authorization", "Bearer x")]


def test_response_fields_named_by_connection_are_hop_by_hop() -> None:
    """H-05: the same rule the other way round, so the upstream's per-hop state dies at this hop."""
    headers = [("connection", "X-Upstream-Hop"), ("x-upstream-hop", "lb-3"), ("content-type", "text/plain")]

    assert forward_response_headers(headers) == [("content-type", "text/plain")]


def test_response_drops_the_normalization_header_of_the_upstream() -> None:
    """H-07..H-12, ADR-007: that header is evalgate's own declaration. Only the proxy may emit it."""
    headers = [(NORMALIZED_HEADER, "choices.logprobs"), ("content-type", "application/json")]

    assert forward_response_headers(headers) == [("content-type", "application/json")]


def test_response_drops_the_fields_the_serving_layer_regenerates() -> None:
    """H-01: the proxy's own HTTP server writes `Date` and `Server`; forwarding them duplicates both."""
    headers = [("date", "Mon, 01 Jan 2027 00:00:00 GMT"), ("server", "cloudflare"), ("x-request-id", "abc")]

    assert forward_response_headers(headers) == [("x-request-id", "abc")]


@pytest.mark.parametrize(
    ("body", "expected"),
    [
        (b'{"model":"m","stream":true}', True),
        (b'{"model":"m","stream":false}', False),
        (b'{"model":"m"}', False),
        (b'{"stream":"true"}', False),
        (b"[1, 2]", False),
        (b"not json", False),
        (b"\xff\xfe", False),
    ],
)
def test_is_stream_request(body: bytes, expected: bool) -> None:
    assert is_stream_request(body) is expected


def test_compliant_response_keeps_its_exact_bytes() -> None:
    assert normalize_chat_completion(COMPLIANT_RESPONSE) == (COMPLIANT_RESPONSE, ())


def test_ollama_response_gets_only_the_missing_nullable_fields() -> None:
    body, fixed = normalize_chat_completion(OLLAMA_RESPONSE)
    original = json.loads(OLLAMA_RESPONSE)
    normalized = json.loads(body)

    assert fixed == ("choices.logprobs", "choices.message.refusal")
    assert normalized["choices"][0]["logprobs"] is None
    assert normalized["choices"][0]["message"]["refusal"] is None
    del normalized["choices"][0]["logprobs"], normalized["choices"][0]["message"]["refusal"]
    assert normalized == original


def test_normalization_keeps_unicode_as_utf8() -> None:
    body, _ = normalize_chat_completion(OLLAMA_RESPONSE)

    assert "¡Hola!".encode() in body


def test_each_normalized_path_is_reported_once_across_choices() -> None:
    two_choices = json.dumps(
        {"choices": [{"index": i, "message": {"role": "assistant", "content": "x"}} for i in range(2)]}
    ).encode()

    assert normalize_chat_completion(two_choices)[1] == ("choices.logprobs", "choices.message.refusal")


@pytest.mark.parametrize(
    "body",
    [
        b"not json",
        b'{"error": {"message": "model not found"}}',
        b'{"choices": "nope"}',
        b'{"choices": [1, 2]}',
        b"[]",
    ],
)
def test_bodies_without_choice_objects_are_returned_untouched(body: bytes) -> None:
    assert normalize_chat_completion(body) == (body, ())


def words(text: str) -> int:
    """The injected tokenizer, as crude here as in production. `translate` does not bring one."""
    return len(text.split())


def test_a_non_streaming_response_is_accounted_from_the_providers_usage_block() -> None:
    """G-TOKENS-EXACT: what gets recorded is the provider's own number, not an estimate over the text."""
    record = record_of_completion(OLLAMA_RESPONSE, words)

    assert record is not None
    assert record.usage == Usage(input_tokens=15, output_tokens=4, source=SOURCE_PROVIDER)
    assert (record.text, record.chunks, record.finish_reason, record.end) == ("¡Hola!", 0, "stop", END_DONE)


def test_without_a_usage_block_a_response_is_estimated_and_says_so() -> None:
    body = b'{"choices":[{"index":0,"message":{"role":"assistant","content":"dos palabras"}}]}'

    record = record_of_completion(body, words)

    assert record is not None
    assert record.usage == Usage(input_tokens=0, output_tokens=2, source=SOURCE_ESTIMATED)


def test_the_reasoning_of_a_non_streaming_response_is_counted_and_kept_apart() -> None:
    """Same rule as the stream (ADR-010): billed, so counted; not the answer, so not in `text`."""
    body = b'{"choices":[{"message":{"content":"","reasoning":"pienso luego cuento"}}]}'

    record = record_of_completion(body, words)

    assert record is not None
    assert (record.text, record.reasoning) == ("", "pienso luego cuento")
    assert record.usage.output_tokens == 3


@pytest.mark.parametrize(
    "body",
    [
        b'{"error":{"message":"model not found","type":"api_error"}}',
        b"not json",
        b"\xff\xfe",
        b'{"choices":"nope"}',
    ],
)
def test_what_cannot_be_read_is_not_accounted(body: bytes) -> None:
    """Inventing a zero is not "not accounting": it is accounting it wrong."""
    assert record_of_completion(body, words) is None


def test_a_non_streaming_record_names_the_model_that_answered() -> None:
    record = record_of_completion(OLLAMA_RESPONSE, words)

    assert record is not None
    assert record.model == "qwen3.5:4b-mlx"


# F3 · de la petición y el registro de uso al `LlmCall` que se traza. Funciones puras: el reloj y el
# proveedor llegan como argumentos.

ORIGIN = CallOrigin("ollama", "http://h/v1")
CHAT_REQUEST = (
    b'{"model":"qwen3.5:4b-mlx","messages":[{"role":"user","content":"hola"}],'
    b'"temperature":0,"max_tokens":64}'
)


def test_request_facts_reads_model_and_sampling_without_keeping_the_prompt() -> None:
    facts = request_facts(CHAT_REQUEST)

    assert facts == RequestFacts(model="qwen3.5:4b-mlx", temperature=0.0, max_tokens=64)
    assert "hola" not in repr(facts)  # R6: nothing of the conversation survives this function


def test_request_facts_takes_the_newer_max_completion_tokens_too() -> None:
    body = b'{"model":"m","messages":[],"max_completion_tokens":32}'

    assert request_facts(body).max_tokens == 32


@pytest.mark.parametrize(
    "body",
    [b"not json", b"[1, 2]", b'{"messages":[]}', b'{"model":7,"temperature":"hot","max_tokens":1.5}'],
)
def test_request_facts_of_a_body_it_cannot_read_are_empty_not_invented(body: bytes) -> None:
    assert request_facts(body) == RequestFacts(model=None, temperature=None, max_tokens=None)


def test_a_boolean_is_not_a_temperature() -> None:
    """In Python `True` is an `int`; in JSON it is not a number, and `temperature: true` is not 1.0."""
    assert request_facts(b'{"model":"m","temperature":true,"max_tokens":false}') == RequestFacts(
        "m", None, None
    )


def test_llm_call_of_a_finished_non_streaming_answer() -> None:
    record = record_of_completion(OLLAMA_RESPONSE, words)
    assert record is not None

    call = llm_call(
        record,
        request_facts(CHAT_REQUEST),
        CallOrigin(provider="ollama", upstream_base_url="http://localhost:11434/v1"),
        started_ns=1_000,
        ended_ns=5_000,
    )

    assert call == LlmCall(
        operation="chat",
        provider="ollama",
        server_address="localhost",
        request_model="qwen3.5:4b-mlx",
        response_model="qwen3.5:4b-mlx",
        input_tokens=15,
        output_tokens=4,
        usage_source=SOURCE_PROVIDER,
        finish_reasons=("stop",),
        started_ns=1_000,
        ended_ns=5_000,
        temperature=0.0,
        max_tokens=64,
    )


def test_llm_call_of_a_hang_up_flags_it_and_measures_ttft_from_the_request() -> None:
    record = UsageRecord(
        Usage(0, 2, SOURCE_ESTIMATED), "El precio ", 3, None, END_CLIENT_DISCONNECT, 0, "", "m", 3_500_000
    )

    call = llm_call(
        record, RequestFacts("m", None, None), CallOrigin("ollama", "http://h:1/v1"), 1_000_000, 9_000_000
    )

    assert (call.client_disconnected, call.error_type, call.finish_reasons) == (True, None, ())
    assert call.ttft_ms == 2.5


@pytest.mark.parametrize(
    ("end", "error_type"),
    [
        (END_DONE, None),
        (END_TIMEOUT, "timeout"),
        (END_ERROR, "provider_error"),
        (END_UPSTREAM_EOF, "upstream_cutoff"),
    ],
)
def test_how_the_stream_ended_becomes_a_low_cardinality_error_type(end: str, error_type: str | None) -> None:
    record = UsageRecord(Usage(1, 1, SOURCE_PROVIDER), "x", 1, "stop", end, 0)

    call = llm_call(record, RequestFacts("m", None, None), ORIGIN, 0, 1)

    assert call.error_type == error_type


def test_a_request_that_named_no_model_is_traced_with_an_empty_request_model() -> None:
    """The provider answered and billed it: the span exists. What the client asked for is "nothing"."""
    record = UsageRecord(Usage(1, 1, SOURCE_PROVIDER), "x", 0, "stop", END_DONE, 0, "", "m")

    call = llm_call(record, RequestFacts(None, None, None), ORIGIN, 0, 1)

    assert (call.request_model, call.response_model) == ("", "m")
