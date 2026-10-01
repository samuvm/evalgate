"""R6 and the mounting of F3: the real pipeline, proxy → `LlmCall` → span → bounded queue → exporter.

**The proxy does not persist the content of prompts by default** (RULES R6). A canary string travels in the
client's message AND in the provider's answer, streaming and not, and it must not appear anywhere in what
reaches the exporter: attribute values, span name, nothing. The model has no field for it (telemetry/model.py)
and this is where that design is checked against the real wiring, not against itself.

The same pipeline is what `evalgate serve` mounts: the sink is `emit_span` over a tracer whose only
processor is the bounded one. An in-memory exporter stands in for ClickHouse; the real store, killed
mid-test, is level 2.
"""

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evalgate.proxy.app import ProxySettings, create_app
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.processor import BoundedSpanProcessor
from evalgate.telemetry.translate import emit_span

from ._proxy import UPSTREAM, Upstream

CANARY = "canario-7f3a9c-no-debe-salir"
CHAT = "/v1/chat/completions"
ASKED = (
    b'{"model":"qwen3.5:4b-mlx","temperature":0,"max_tokens":64,'
    b'"messages":[{"role":"user","content":"' + CANARY.encode() + b'"}]'
)
ANSWER = (
    b'{"id":"c1","object":"chat.completion","created":1,"model":"qwen3.5:4b-mlx","choices":[{"index":0,'
    b'"message":{"role":"assistant","content":"' + CANARY.encode() + b'"},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":15,"completion_tokens":4,"total_tokens":19}}'
)
STREAMED = b"".join(
    b"data: " + chunk + b"\n\n"
    for chunk in (
        b'{"id":"c2","object":"chat.completion.chunk","created":1,"model":"qwen3.5:4b-mlx",'
        b'"choices":[{"index":0,"delta":{"role":"assistant","content":""},"finish_reason":null}]}',
        b'{"id":"c2","object":"chat.completion.chunk","created":1,"model":"qwen3.5:4b-mlx",'
        b'"choices":[{"index":0,"delta":{"content":"' + CANARY.encode() + b'"},"finish_reason":null}]}',
        b'{"id":"c2","object":"chat.completion.chunk","created":1,"model":"qwen3.5:4b-mlx",'
        b'"choices":[{"index":0,"delta":{},"finish_reason":"stop"}]}',
        b'{"id":"c2","object":"chat.completion.chunk","created":1,"model":"qwen3.5:4b-mlx","choices":[],'
        b'"usage":{"prompt_tokens":15,"completion_tokens":4,"total_tokens":19}}',
        b"[DONE]",
    )
)


class Pipeline:
    """The proxy mounted the way `evalgate serve` mounts it, with an in-memory store at the end."""

    def __init__(self, upstream: Upstream, on_call: Any = None) -> None:
        self.store = InMemorySpanExporter()
        self.processor = BoundedSpanProcessor(self.store, capacity=64, batch_size=8)
        provider = TracerProvider()
        provider.add_span_processor(self.processor)
        tracer = provider.get_tracer("evalgate")
        sink = on_call or (lambda call: emit_span(tracer, call))
        settings = ProxySettings(upstream_base_url=UPSTREAM, on_call=sink)
        client = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
        self.client = TestClient(create_app(settings, client=client))

    def spans(self) -> list[ReadableSpan]:
        assert self.processor.force_flush()
        return list(self.store.get_finished_spans())


@pytest.fixture
def served() -> Iterator[list[Pipeline]]:
    pipelines: list[Pipeline] = []
    yield pipelines
    for pipeline in pipelines:
        pipeline.processor.shutdown()


def mount(served: list[Pipeline], upstream: Upstream, on_call: Any = None) -> Pipeline:
    served.append(Pipeline(upstream, on_call))
    return served[-1]


def leaked(span: ReadableSpan) -> list[str]:
    places = {"name": span.name, **{key: str(value) for key, value in (span.attributes or {}).items()}}
    return [where for where, text in places.items() if CANARY in text]


def test_a_non_streaming_call_is_traced_without_its_conversation(served: list[Pipeline]) -> None:
    pipeline = mount(served, Upstream(body=ANSWER))

    response = pipeline.client.post(CHAT, content=ASKED + b"}")

    assert CANARY.encode() in response.content, "the client does get the answer: only the trace omits it"
    (span,) = pipeline.spans()
    assert leaked(span) == []
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.request.model"] == attributes["gen_ai.response.model"] == "qwen3.5:4b-mlx"
    assert (attributes["gen_ai.usage.input_tokens"], attributes["gen_ai.usage.output_tokens"]) == (15, 4)
    assert (attributes["gen_ai.request.temperature"], attributes["gen_ai.request.max_tokens"]) == (0.0, 64)
    assert attributes["server.address"] == "upstream.test"
    assert "app.ttft_ms" not in attributes  # there is no first token without a stream


def test_a_streamed_call_is_traced_without_its_conversation_and_with_its_ttft(served: list[Pipeline]) -> None:
    pipeline = mount(served, Upstream(body=STREAMED, headers={"content-type": "text/event-stream"}))

    response = pipeline.client.post(CHAT, content=ASKED + b',"stream":true}')

    assert CANARY.encode() in response.content
    (span,) = pipeline.spans()
    assert leaked(span) == []
    attributes = dict(span.attributes or {})
    assert attributes["gen_ai.response.finish_reasons"] == ("stop",)
    assert attributes["app.usage.source"] == "provider"
    assert attributes["app.stream.client_disconnected"] is False
    ttft = attributes["app.ttft_ms"]
    assert isinstance(ttft, float)
    assert 0 <= ttft <= (span.end_time or 0) / 1e6 - (span.start_time or 0) / 1e6


def test_a_sink_that_raises_never_reaches_the_client(served: list[Pipeline]) -> None:
    """R1 at the mounting: observability that breaks can cost a trace, never a request."""

    def broken(call: LlmCall) -> None:
        raise RuntimeError(f"the store is on fire, {call.request_model} lost")

    pipeline = mount(served, Upstream(body=ANSWER), on_call=broken)

    response = pipeline.client.post(CHAT, content=ASKED + b"}")

    assert response.status_code == 200
    assert CANARY.encode() in response.content
