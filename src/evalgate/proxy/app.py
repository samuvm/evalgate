"""FastAPI app of the proxy. I/O and wiring only: excluded from unit tests (RULES §2), covered by
tests/contract (byte-for-byte passthrough, OpenAPI schema, token reconciliation) and tests/e2e (adoption).

Here is where the two pure halves get mounted: `translate` decides what to forward, `streaming` counts what
the provider emitted. This file only moves bytes and chooses who to hand them to."""

import contextlib
import os
import time
from collections.abc import AsyncGenerator, AsyncIterator, Callable
from contextlib import asynccontextmanager
from dataclasses import dataclass

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response, StreamingResponse
from starlette.types import Receive, Scope, Send

from evalgate.proxy.streaming import StreamAccountant, UsageRecord, relay
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

DEFAULT_UPSTREAM = "http://localhost:11434/v1"  # Ollama runs on the host, never in compose (STACK §0)
DEFAULT_PROVIDER = "ollama"  # D-05: local models only, for now


def whitespace_tokens(text: str) -> int:
    """Fallback count for when the provider sends no `usage` block. Crude ON PURPOSE and always declared.

    Measured against Ollama 0.33.3 on 2026-09-12 it is 35-57 % off the provider's own number, so it is a
    floor for "something was emitted here", never a bill. Every record it feeds carries `source: estimated`,
    and PARA-SAMUEL P-005 decides what may be published from it. Whoever mounts the proxy can inject a
    better one: this module does not get to pick a tokenizer for the whole project.
    """
    return len(text.split())


@dataclass(frozen=True, slots=True)
class ProxySettings:
    upstream_base_url: str = DEFAULT_UPSTREAM
    # PARA-SAMUEL P-004 (a), ADR-007: add the schema's missing nullable fields when the upstream omits them.
    normalize: bool = True
    connect_timeout_s: float = 5.0
    read_timeout_s: float = 600.0
    # R1: the sinks are CALLED, never awaited, and they can never take the request down. `on_usage` gets the
    # raw accounting; `on_call` the trace of the call, which whoever mounts the proxy hands to a bounded queue
    # (telemetry/processor.py). `None` means nobody is listening. `proxy/` never sees an exporter (R1, rule).
    on_usage: Callable[[UsageRecord], None] | None = None
    on_call: Callable[[LlmCall], None] | None = None
    count_tokens: Callable[[str], int] = whitespace_tokens
    provider: str = DEFAULT_PROVIDER
    clock: Callable[[], int] = time.time_ns  # epoch ns, OpenTelemetry's clock; injected so tests can pin it

    @property
    def origin(self) -> CallOrigin:
        return CallOrigin(self.provider, self.upstream_base_url)

    @classmethod
    def from_env(cls) -> "ProxySettings":
        return cls(
            upstream_base_url=os.environ.get("EVALGATE_UPSTREAM_BASE_URL", DEFAULT_UPSTREAM),
            normalize=os.environ.get("EVALGATE_NORMALIZE", "on").lower() in {"on", "1", "true"},
            provider=os.environ.get("EVALGATE_PROVIDER", DEFAULT_PROVIDER),
        )


def openai_error(status: int, message: str, kind: str) -> JSONResponse:
    """Error body with the shape of the OpenAI `ErrorResponse` schema."""
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": kind, "param": None, "code": None}},
    )


def emit(config: ProxySettings, record: UsageRecord | None, request: RequestFacts, started_ns: int) -> None:
    """Hand the usage record and the trace of the call to whoever is listening. R1: no `await`, and no way
    to fail the request.

    A sink that raises would turn observability into an outage, which is the one thing R1 forbids. What a
    full queue drops is counted there (`app.spans.dropped`), not here: here nothing waits to be dropped.
    """
    if record is None:
        return
    if config.on_usage is not None:
        with contextlib.suppress(Exception):
            config.on_usage(record)
    if config.on_call is not None:
        with contextlib.suppress(Exception):
            config.on_call(llm_call(record, request, config.origin, started_ns, config.clock()))


def raw(headers: list[tuple[str, str]]) -> list[tuple[bytes, bytes]]:
    """Header lines for the ASGI layer. `latin-1` is its encoding, the same one starlette uses."""
    return [(name.encode("latin-1"), value.encode("latin-1")) for name, value in headers]


class AccountedStream(StreamingResponse):
    """A streaming response that closes its body **inside the ASGI call**, on every path.

    `StreamingResponse` walks the body with `async for`, and `async for` does not close what it walks. When
    the client hangs up, starlette cancels the streaming task while the generator is suspended on its
    `yield`; the loop leaves through that cancellation and nobody ever closes the generator. Its `finally`
    -- the one R2 demands -- then runs whenever the garbage collector gets to the reference cycle: outside
    the request that paid for those tokens, and not at all if the process dies first. That is H-13 of
    `docs/qa/hallazgos-F2.md`, and it is a defect of the MOUNTING, not of the module: `relay`'s `finally` is
    correct, and somebody still has to pull its trigger while the request is still the request.

    So the closing goes in a `finally` around the whole ASGI call, which is the only place that covers the
    three exits starlette has (the body ran out, the client hung up and the task got cancelled, or the
    2.4-and-later path raised `ClientDisconnect`). `scripts/rules/stream_closed_in_request.py` is the
    mechanical half: it forbids mounting a bare `StreamingResponse` anywhere in `proxy/`.
    """

    def __init__(self, body: AsyncGenerator[bytes, None], status_code: int) -> None:
        super().__init__(body, status_code=status_code)
        # Held under our own name and type on purpose: `body_iterator` is declared as a plain
        # `AsyncIterable`, which has no `aclose`, and the closing is this class's whole reason to exist.
        self.closable = body

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        try:
            await super().__call__(scope, receive, send)
        finally:
            # Idempotent: on the happy path the generator is already exhausted and this is a no-op. On a
            # hang-up it throws `GeneratorExit` at the suspended `yield`, which is what makes the record
            # come out here, synchronously, before this call returns.
            await self.closable.aclose()


async def streamed(
    http: httpx.AsyncClient, url: str, body: bytes, headers: list[tuple[str, str]], config: ProxySettings
) -> Response:
    """Forward an SSE response chunk by chunk while the accountant counts what the provider emitted."""
    accountant = StreamAccountant(count_tokens=config.count_tokens, clock=config.clock)
    facts = request_facts(body)
    try:
        asked = http.build_request("POST", url, content=body, headers=headers)
        started = config.clock()  # TTFT and the span start from here: the request leaving for the provider
        upstream = await http.send(asked, stream=True)
    except httpx.HTTPError as exc:
        return openai_error(502, f"evalgate: upstream unreachable ({type(exc).__name__})", "upstream_error")

    if upstream.status_code != httpx.codes.OK:
        # An error is not a stream: it is one JSON body, so it is read whole and handed over like any other.
        await upstream.aread()
        content = upstream.content
        await upstream.aclose()
        failed = Response(content=content, status_code=upstream.status_code)
        failed.raw_headers.extend(raw(forward_response_headers(upstream.headers.multi_items())))
        return failed

    async def forwarded() -> AsyncGenerator[bytes, None]:
        stream = relay(
            upstream.aiter_bytes(), accountant, lambda record: emit(config, record, facts, started)
        )
        try:
            async for piece in stream:
                yield piece
        finally:
            # Closed explicitly, not left to the garbage collector: the record has to come out NOW, while
            # the request is still the request. R2.
            await stream.aclose()
            await upstream.aclose()

    response = AccountedStream(forwarded(), upstream.status_code)
    response.raw_headers.extend(raw(forward_response_headers(upstream.headers.multi_items())))
    return response


def create_app(settings: ProxySettings | None = None, client: httpx.AsyncClient | None = None) -> FastAPI:
    """Build the proxy. Pass `client` to inject the upstream transport (tests); otherwise one is created."""
    config = settings or ProxySettings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        if client is not None:
            yield
            return
        timeout = httpx.Timeout(config.read_timeout_s, connect=config.connect_timeout_s)
        async with httpx.AsyncClient(timeout=timeout) as own:
            app.state.client = own
            yield

    app = FastAPI(title="evalgate proxy", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.client = client

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok", "upstream": config.upstream_base_url}

    @app.post("/v1/chat/completions")
    async def chat_completions(request: Request) -> Response:
        body = await request.body()
        http: httpx.AsyncClient = request.app.state.client
        # The pinned OpenAPI declares no query parameter here, so the proxy has no ground to drop one:
        # what it does not understand, it forwards, raw and byte for byte (e.g. Azure's `api-version`).
        url = upstream_url(config.upstream_base_url, "chat/completions")
        if request.url.query:
            url = f"{url}?{request.url.query}"
        # `.items()` and not the mapping itself: starlette repeats a field that arrived twice.
        headers = forward_request_headers(request.headers.items())

        if is_stream_request(body):
            return await streamed(http, url, body, headers, config)

        started = config.clock()
        try:
            upstream = await http.post(url, content=body, headers=headers)
        except httpx.HTTPError as exc:
            return openai_error(
                502, f"evalgate: upstream unreachable ({type(exc).__name__})", "upstream_error"
            )

        content = upstream.content
        # Accounted from what the PROVIDER said, before any normalization of ours touches the body.
        emit(config, record_of_completion(content, config.count_tokens), request_facts(body), started)
        # `.multi_items()` and not `.items()`: httpx joins repeated fields with a comma, which corrupts a
        # `Set-Cookie` whose `expires` date already carries one (RFC 6265 §3).
        headers_back = forward_response_headers(upstream.headers.multi_items())
        if config.normalize and upstream.status_code == httpx.codes.OK:
            content, fixed = normalize_chat_completion(content)
            if fixed:
                headers_back.append((NORMALIZED_HEADER, ",".join(fixed)))
        # Built without `headers=`, which takes a mapping and would merge the repetitions back: starlette
        # computes `content-length` for the body actually sent, and the upstream's lines are appended as
        # they came.
        response = Response(content=content, status_code=upstream.status_code)
        response.raw_headers.extend(raw(headers_back))
        return response

    return app
