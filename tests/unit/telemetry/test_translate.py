"""The translator by example: one real call, one span, every attribute written out.

The contract test (tests/contract/test_otel_attrs.py) holds every generated call to the contract; this one
pins what a concrete, recognisable call turns into, so a reader can see the translation without Hypothesis.
"""

from dataclasses import replace
from decimal import Decimal

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from evalgate.telemetry.model import Cost, LlmCall
from evalgate.telemetry.translate import attributes, emit_span, span_name

# A streamed answer of Ollama whose client hung up: the case this project exists for.
CALL = LlmCall(
    operation="chat",
    provider="ollama",
    server_address="localhost",
    request_model="qwen3.5:4b-mlx",
    response_model="qwen3.5:4b-mlx",
    input_tokens=15,
    output_tokens=4,
    usage_source="provider",
    finish_reasons=("stop",),
    started_ns=1_789_045_001_000_000_000,
    ended_ns=1_789_045_001_250_000_000,
    client_disconnected=True,
    ttft_ms=48.5,
)


def test_attributes_of_a_plain_call_are_the_mandatory_ones_and_no_more() -> None:
    assert attributes(CALL) == {
        "gen_ai.operation.name": "chat",
        "gen_ai.provider.name": "ollama",
        "gen_ai.request.model": "qwen3.5:4b-mlx",
        "gen_ai.response.model": "qwen3.5:4b-mlx",
        "gen_ai.usage.input_tokens": 15,
        "gen_ai.usage.output_tokens": 4,
        "gen_ai.response.finish_reasons": ("stop",),
        "server.address": "localhost",
        "app.stream.client_disconnected": True,
        "app.usage.source": "provider",
        "app.ttft_ms": 48.5,
    }


def test_optional_attributes_appear_only_when_the_call_has_them() -> None:
    full = replace(
        CALL,
        temperature=0.0,
        max_tokens=256,
        error_type="timeout",
        cost=Cost(eur=Decimal("0.000123"), pricing_version="2026-09-01"),
    )

    extra = attributes(full).items() - attributes(CALL).items()

    # temperature 0.0 is a value, not an absence: `if call.temperature:` would drop the most common setting.
    assert extra == {
        ("gen_ai.request.temperature", 0.0),
        ("gen_ai.request.max_tokens", 256),
        ("error.type", "timeout"),
        ("app.cost.eur", 0.000123),
        ("app.cost.pricing_version", "2026-09-01"),
    }


def test_a_model_the_provider_never_named_is_absent_not_guessed() -> None:
    """PARA-SAMUEL Q-011 (a), provisional: a zero-length stream never says who answered. The request's model
    is right there and it would be a guess; the attribute is left out instead."""
    out = attributes(replace(CALL, response_model=None))

    assert "gen_ai.response.model" not in out
    assert out["gen_ai.request.model"] == "qwen3.5:4b-mlx"


def test_span_name_is_operation_then_requested_model() -> None:
    assert span_name(CALL) == "chat qwen3.5:4b-mlx"


def test_emit_span_ends_a_client_span_at_the_call_times() -> None:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))

    emit_span(provider.get_tracer("evalgate"), replace(CALL, error_type="timeout"))

    (span,) = exporter.get_finished_spans()
    assert span.name == "chat qwen3.5:4b-mlx"
    assert span.kind is SpanKind.CLIENT
    assert (span.start_time, span.end_time) == (CALL.started_ns, CALL.ended_ns)
    assert span.status.status_code is StatusCode.ERROR
    assert dict(span.attributes or {}) == attributes(replace(CALL, error_type="timeout"))
