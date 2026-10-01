"""Translator from the internal model (`LlmCall`) to an OpenTelemetry span: contract otel-genai §2.

The ONLY module that knows the external names, and it does not write them either: it takes them from
`telemetry/semconv/`, generated from the commit `otel-semconv.lock` pins (R5). When the spec breaks again,
this file and the lock are the whole change.

Our own extensions go in the `app.*` namespace the contract reserves for them (§4), never inside
`gen_ai.*`: inventing names there is what makes the traces useless to any third-party tool.
"""

from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from opentelemetry.util.types import AttributeValue

from evalgate.telemetry import semconv
from evalgate.telemetry.model import LlmCall

# Contract otel-genai §4, "Extensiones propias". `app.usage.source` is ours too: P-005 (a) wants every
# record to say whether its tokens are the provider's or an estimate, and a span is a record.
APP_COST_EUR = "app.cost.eur"
APP_COST_PRICING_VERSION = "app.cost.pricing_version"
APP_STREAM_CLIENT_DISCONNECTED = "app.stream.client_disconnected"
APP_TTFT_MS = "app.ttft_ms"
APP_USAGE_SOURCE = "app.usage.source"


def span_name(call: LlmCall) -> str:
    """`{operation} {requested model}`, as the pinned spans.yaml names the inference span."""
    return f"{call.operation} {call.request_model}"


def attributes(call: LlmCall) -> dict[str, AttributeValue]:
    """Every fact of the call, under the pinned external names. Optional ones only when the call has them.

    `is not None` and never truthiness: a temperature of 0.0 and a cost of 0 € are values, and the most
    common ones in this project (deterministic runs, local models).
    """
    out: dict[str, AttributeValue] = {
        semconv.OPERATION_NAME: call.operation,
        semconv.PROVIDER_NAME: call.provider,
        semconv.REQUEST_MODEL: call.request_model,
        semconv.USAGE_INPUT_TOKENS: call.input_tokens,
        semconv.USAGE_OUTPUT_TOKENS: call.output_tokens,
        semconv.RESPONSE_FINISH_REASONS: call.finish_reasons,
        semconv.SERVER_ADDRESS: call.server_address,
        APP_STREAM_CLIENT_DISCONNECTED: call.client_disconnected,
        APP_USAGE_SOURCE: call.usage_source,
    }
    if call.response_model is not None:  # Q-011 (a), provisional: absent beats invented
        out[semconv.RESPONSE_MODEL] = call.response_model
    if call.temperature is not None:
        out[semconv.REQUEST_TEMPERATURE] = call.temperature
    if call.max_tokens is not None:
        out[semconv.REQUEST_MAX_TOKENS] = call.max_tokens
    if call.error_type is not None:
        out[semconv.ERROR_TYPE] = call.error_type
    if call.ttft_ms is not None:
        out[APP_TTFT_MS] = call.ttft_ms
    if call.cost is not None:
        # A float on the wire because OTel has no decimal type; the exact Decimal stays in the model, which
        # is where the cost report reads it from (G-PRICE-REPRO is computed there, not from spans).
        out[APP_COST_EUR] = float(call.cost.eur)
        out[APP_COST_PRICING_VERSION] = call.cost.pricing_version
    return out


def emit_span(tracer: Tracer, call: LlmCall) -> None:
    """Record the call as one finished CLIENT span, with the call's own start and end times.

    The span is built after the fact from a closed record, never held open around the request: that is
    what lets the proxy hand records to a queue and forget them (R1).
    """
    span = tracer.start_span(
        span_name(call), kind=SpanKind.CLIENT, attributes=attributes(call), start_time=call.started_ns
    )
    if call.error_type is not None:
        span.set_status(Status(StatusCode.ERROR))
    span.end(end_time=call.ended_ns)
