"""G-OTEL-CONTRACT: every span the translator emits carries what `docs/CONTRACTS/otel-genai.md` §4 demands.

The spans are real: they go through the OpenTelemetry SDK into an in-memory exporter and are read back as
any backend would read them. Checking the dict the translator returns would test the translator against
itself; the span is what leaves the process.

The attribute names are written here LITERALLY, copied from the contract, on purpose (same reason as in
`test_semconv_generated.py`): if the contract changes, this test must fail and force someone to look, not
adapt itself by reading the same module the translator reads. R5 forbids `gen_ai.*` literals in `src/`,
not in the tests that hold `src/` to the contract.

What "translation is total" means here, the second half of the goal: every field of `LlmCall` that has a
value reaches the span with that value, and nothing reaches the span that the pinned version does not
declare. A field the translator forgot would be an internal-model fact that no backend ever sees.
"""

from typing import Any

from hypothesis import given
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
from opentelemetry.trace import SpanKind, StatusCode

from evalgate.telemetry import semconv
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.translate import emit_span
from tests._llm_calls import llm_calls
from tests._meter import Meter

GOAL = "G-OTEL-CONTRACT"

# Contrato §4, span de invocación, las filas "sí": tienen que estar SIEMPRE. Con una excepción, provisional y
# preguntada (PARA-SAMUEL Q-011, opción (a)): `gen_ai.response.model` se exige siempre que el proveedor dijo
# qué modelo respondió, y falta solo cuando no lo dijo. Inventarlo sería peor que omitirlo.
SIEMPRE = {
    "gen_ai.operation.name": str,
    "gen_ai.provider.name": str,
    "gen_ai.request.model": str,
    "gen_ai.response.model": str,
    "gen_ai.usage.input_tokens": int,
    "gen_ai.usage.output_tokens": int,
    "gen_ai.response.finish_reasons": tuple,
    "server.address": str,
}
# Extensiones propias del contrato §4 que G-OTEL-CONTRACT nombra, más la procedencia del recuento
# (P-005 (a)): un número estimado que viaja sin decirlo se lee como factura.
SIEMPRE_APP = {
    "app.stream.client_disconnected": bool,
    "app.usage.source": str,
}
# Las filas "si aplica" / "si hay error", y las extensiones que solo existen a veces.
SI_APLICA = {
    "gen_ai.request.temperature": float,
    "gen_ai.request.max_tokens": int,
    "error.type": str,
    "app.ttft_ms": float,
    "app.cost.eur": float,
    "app.cost.pricing_version": str,
}
RESPONSE_MODEL = "gen_ai.response.model"
APP_DECLARADOS = set(SIEMPRE_APP) | {k for k in SI_APLICA if k.startswith("app.")}


def spans_of(call: LlmCall) -> list[ReadableSpan]:
    exporter = InMemorySpanExporter()
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    emit_span(provider.get_tracer("evalgate"), call)
    provider.shutdown()
    return list(exporter.get_finished_spans())


def expected(call: LlmCall) -> dict[str, Any]:
    """What the contract says this call's span must carry. Written from the contract, not the translator."""
    values: dict[str, Any] = {
        "gen_ai.operation.name": call.operation,
        "gen_ai.provider.name": call.provider,
        "gen_ai.request.model": call.request_model,
        "gen_ai.usage.input_tokens": call.input_tokens,
        "gen_ai.usage.output_tokens": call.output_tokens,
        "gen_ai.response.finish_reasons": call.finish_reasons,
        "server.address": call.server_address,
        "app.stream.client_disconnected": call.client_disconnected,
        "app.usage.source": call.usage_source,
    }
    optional = {
        "gen_ai.response.model": call.response_model,
        "gen_ai.request.temperature": call.temperature,
        "gen_ai.request.max_tokens": call.max_tokens,
        "error.type": call.error_type,
        "app.ttft_ms": call.ttft_ms,
        "app.cost.eur": None if call.cost is None else float(call.cost.eur),
        "app.cost.pricing_version": None if call.cost is None else call.cost.pricing_version,
    }
    values.update({key: value for key, value in optional.items() if value is not None})
    return values


def violations(call: LlmCall, span: ReadableSpan) -> list[str]:
    found = dict(span.attributes or {})
    wanted = expected(call)
    required = [k for k in (*SIEMPRE, *SIEMPRE_APP) if k != RESPONSE_MODEL or call.response_model is not None]
    problems = [f"falta {key}" for key in required if key not in found]
    problems += [
        f"{key}={found.get(key)!r}, esperado {value!r}"
        for key, value in wanted.items()
        if found.get(key) != value
    ]
    problems += [f"{key} sobra: la llamada no lo tiene" for key in found if key not in wanted]
    types = SIEMPRE | SIEMPRE_APP | SI_APLICA
    problems += [
        f"{key} es {type(value).__name__}, no {types[key].__name__}"
        for key, value in found.items()
        if key in types and not isinstance(value, types[key])
    ]
    # La versión pineada: ningún nombre externo que el registro vendorizado no declare, y nada propio
    # fuera del namespace `app.*` que el contrato reserva (§4, "nunca gen_ai.*").
    problems += [
        f"{key} no existe en {semconv.SEMCONV_VERSION}"
        for key in found
        if not key.startswith("app.") and key not in semconv.ATTRIBUTE_TYPES
    ]
    problems += [
        f"{key} no es una extensión del contrato"
        for key in found
        if key.startswith("app.") and key not in APP_DECLARADOS
    ]
    return problems


@given(llm_calls())
def test_every_emitted_span_honours_the_contract(meter: Meter, call: LlmCall) -> None:
    spans = spans_of(call)
    assert len(spans) == 1, "una llamada, un span"
    problems = violations(call, spans[0])
    meter.check(GOAL, not problems)
    assert not problems


@given(llm_calls())
def test_span_is_a_client_span_named_after_operation_and_model(call: LlmCall) -> None:
    """Semconv v1.41.1, spans.yaml: `{gen_ai.operation.name} {gen_ai.request.model}`, kind CLIENT."""
    (span,) = spans_of(call)

    assert span.name == f"{call.operation} {call.request_model}"
    assert span.kind is SpanKind.CLIENT
    assert (span.start_time, span.end_time) == (call.started_ns, call.ended_ns)


@given(llm_calls())
def test_an_error_marks_the_span_as_failed_and_only_then(call: LlmCall) -> None:
    (span,) = spans_of(call)

    if call.error_type is None:
        assert span.status.status_code is StatusCode.UNSET
    else:
        assert span.status.status_code is StatusCode.ERROR
