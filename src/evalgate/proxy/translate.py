"""Pure protocol helpers for the proxy: headers, upstream URL, stream detection, schema normalization.

No I/O here: proxy/app.py does the network part and calls these functions.
"""

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlsplit

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
from evalgate.telemetry.model import LlmCall

NORMALIZED_HEADER = "x-evalgate-normalized"

# RFC 9110 §7.6.1 hop-by-hop headers, plus the ones the proxy recomputes itself. It is not the whole rule:
# `Connection` names further fields that die at this hop, and `_dropped()` adds them per message.
_HOP_BY_HOP = frozenset(
    {
        "connection",
        "keep-alive",
        "proxy-authenticate",
        "proxy-authorization",
        "te",
        "trailer",
        "transfer-encoding",
        "upgrade",
        "host",
        "content-length",
    }
)
# The upstream body is read decoded, so its encoding headers no longer describe what the proxy sends.
# `Date` and `Server` are written by the proxy's own HTTP server: forwarding the upstream's would give the
# client two lines of each, and neither is a list field (RFC 9110 §5.3). And NORMALIZED_HEADER is evalgate's
# own declaration that it touched the body (ADR-007): whatever the upstream sends, only this proxy emits it.
_RESPONSE_DROPPED = _HOP_BY_HOP | {"content-encoding", "date", "server", NORMALIZED_HEADER}
# Let the HTTP client negotiate compression with the upstream on its own.
_REQUEST_DROPPED = _HOP_BY_HOP | {"accept-encoding"}


def upstream_url(base_url: str, path: str) -> str:
    """Join the upstream base URL (e.g. `http://localhost:11434/v1`) and an API path."""
    return f"{base_url.rstrip('/')}/{path.lstrip('/')}"


def _dropped(lines: list[tuple[str, str]], always: frozenset[str]) -> set[str]:
    """Field names this hop must not forward: the fixed list plus every token `Connection` names (§7.6.1)."""
    named = {
        token.strip().lower()
        for name, value in lines
        if name.lower() == "connection"
        for token in value.split(",")
        if token.strip()
    }
    return named | always


def _forward(headers: Iterable[tuple[str, str]], always: frozenset[str]) -> list[tuple[str, str]]:
    """Filter header LINES, keeping repetitions and their order: two lines of a field are its list (§5.3).

    Pairs in, pairs out. A `dict` cannot hold a field that appears twice, and collapsing it is never
    harmless: the client loses a value, or two `Set-Cookie` are joined by a comma that RFC 6265 §3 forbids.
    """
    lines = list(headers)
    dropped = _dropped(lines, always)
    return [(name, value) for name, value in lines if name.lower() not in dropped]


def forward_request_headers(headers: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Client header lines to send upstream: everything except hop-by-hop and encoding negotiation."""
    return _forward(headers, _REQUEST_DROPPED)


def forward_response_headers(headers: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
    """Upstream header lines to return to the client: everything except hop-by-hop and what the proxy owns."""
    return _forward(headers, _RESPONSE_DROPPED)


def is_stream_request(body: bytes) -> bool:
    """True if the chat request asks for streaming. Unparseable bodies are left to the upstream."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("stream") is True


def normalize_chat_completion(body: bytes) -> tuple[bytes, tuple[str, ...]]:
    """Add the fields that the OpenAI schema requires and the upstream omitted, with `null`.

    Only `choices[].logprobs` and `choices[].message.refusal` (required-but-nullable in
    CreateChatCompletionResponse). If nothing is missing, the ORIGINAL bytes are returned untouched,
    so a compliant upstream keeps byte-for-byte fidelity. Returns (body, normalized field paths).
    """
    try:
        payload: Any = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return body, ()
    choices = payload.get("choices") if isinstance(payload, dict) else None
    if not isinstance(choices, list):
        return body, ()

    fixed: list[str] = []
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        if "logprobs" not in choice:
            choice["logprobs"] = None
            fixed.append("choices.logprobs")
        message = choice.get("message")
        if isinstance(message, dict) and "refusal" not in message:
            message["refusal"] = None
            fixed.append("choices.message.refusal")
    if not fixed:
        return body, ()
    unique = tuple(dict.fromkeys(fixed))
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"), unique


def record_of_completion(body: bytes, count_tokens: Callable[[str], int]) -> UsageRecord | None:
    """The usage record of a NON-streaming response: one JSON object instead of a stream of frames.

    `None` when the body is not a chat completion —an error from the provider, or something unparseable—.
    What cannot be read is not accounted for: inventing a zero would not be "not accounting", it would be
    accounting it wrong, which is worse.
    """
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or not isinstance(choices := payload.get("choices"), list):
        return None

    text, reasoning, finish_reason = "", "", None
    for choice in choices:
        if not isinstance(choice, dict):
            continue
        message = choice.get("message")
        if isinstance(message, dict):
            if isinstance(content := message.get("content"), str):
                text += content
            if isinstance(thought := message.get("reasoning"), str):
                reasoning += thought
        if isinstance(finish := choice.get("finish_reason"), str):
            finish_reason = finish

    usage = payload.get("usage")
    prompt = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion = usage.get("completion_tokens") if isinstance(usage, dict) else None
    if isinstance(prompt, int) and isinstance(completion, int):
        counted = Usage(prompt, completion, SOURCE_PROVIDER)
    else:
        counted = Usage(0, count_tokens(text) + count_tokens(reasoning), SOURCE_ESTIMATED)
    model = payload.get("model")
    # `chunks=0` porque no hubo ninguno: una respuesta no-streaming no es un stream de longitud 1.
    return UsageRecord(
        counted, text, 0, finish_reason, END_DONE, 0, reasoning, model if isinstance(model, str) else None
    )


@dataclass(frozen=True, slots=True)
class RequestFacts:
    """What the trace needs from the client's request, and nothing else: no message survives this (R6)."""

    model: str | None
    temperature: float | None
    max_tokens: int | None


def _number(value: Any) -> float | None:
    # `bool` is an `int` in Python and not a number in JSON: `temperature: true` is not 1.0.
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


def _whole(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def request_facts(body: bytes) -> RequestFacts:
    """Model and sampling parameters of a chat request. A field that is absent or of the wrong type is `None`:
    the proxy forwards what it cannot read, and it does not trace what it did not see."""
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    if not isinstance(payload, dict):
        return RequestFacts(None, None, None)
    model = payload.get("model")
    # `max_completion_tokens` is the newer name OpenAI gives the same limit; either one is the request's cap.
    cap = _whole(payload.get("max_tokens"))
    return RequestFacts(
        model if isinstance(model, str) else None,
        _number(payload.get("temperature")),
        cap if cap is not None else _whole(payload.get("max_completion_tokens")),
    )


@dataclass(frozen=True, slots=True)
class CallOrigin:
    """Who serves the calls of this proxy: fixed at mount time, the same for every request."""

    provider: str  # "ollama", "openai"…
    upstream_base_url: str


# How a stream ended, as `error.type` (low cardinality, as the semconv asks). A client hanging up is not an
# error of the call —the answer was fine, nobody stayed to read it— and has its own flag.
_ERROR_OF_END = {END_TIMEOUT: "timeout", END_ERROR: "provider_error", END_UPSTREAM_EOF: "upstream_cutoff"}


def llm_call(
    record: UsageRecord,
    request: RequestFacts,
    origin: CallOrigin,
    started_ns: int,
    ended_ns: int,
) -> LlmCall:
    """The trace of one served chat call. Pure: the clock readings and the origin come in as arguments.

    `request_model` is `""` when the client named none: the provider answered and billed it, so the call is
    traced, and what the client asked for was literally nothing.
    """
    ttft_ms = None if record.first_content_ns is None else (record.first_content_ns - started_ns) / 1e6
    return LlmCall(
        operation="chat",
        provider=origin.provider,
        server_address=urlsplit(origin.upstream_base_url).hostname or "",
        request_model=request.model or "",
        response_model=record.model,
        input_tokens=record.usage.input_tokens,
        output_tokens=record.usage.output_tokens,
        usage_source=record.usage.source,
        finish_reasons=() if record.finish_reason is None else (record.finish_reason,),
        started_ns=started_ns,
        ended_ns=ended_ns,
        client_disconnected=record.end == END_CLIENT_DISCONNECT,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        error_type=_ERROR_OF_END.get(record.end),
        ttft_ms=ttft_ms,
    )
