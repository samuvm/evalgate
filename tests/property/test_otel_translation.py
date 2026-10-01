"""The translation is total and speaks only the pinned version: the property half of G-OTEL-CONTRACT.

Checked on the attribute mapping itself, without the SDK in between, so a failure here says "the
translator" and a failure in tests/contract says "what reaches the wire". Names are resolved through the
generated `semconv` module on purpose: this test is about the TRANSLATOR using the pinned vocabulary, and
the literal names are held to the contract elsewhere (tests/contract/test_otel_attrs.py).
"""

from hypothesis import given
from tests._llm_calls import llm_calls

from evalgate.telemetry import semconv
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.translate import attributes

_PYTHON_TYPE = {"string": str, "enum": str, "int": int, "double": float, "boolean": bool, "string[]": tuple}


@given(llm_calls())
def test_every_external_attribute_has_the_type_the_pinned_model_declares(call: LlmCall) -> None:
    for key, value in attributes(call).items():
        if key.startswith("app."):
            continue
        declared = semconv.ATTRIBUTE_TYPES[key]
        assert isinstance(value, _PYTHON_TYPE[declared]), f"{key}: {declared} y llega {type(value).__name__}"
        if declared == "string[]":
            assert all(isinstance(item, str) for item in value)


@given(llm_calls())
def test_no_fact_of_the_call_is_lost_in_translation(call: LlmCall) -> None:
    """Every field with a value comes out. The two timestamps travel as span times, not attributes."""
    out = attributes(call)
    assert out[semconv.USAGE_INPUT_TOKENS] == call.input_tokens
    assert out[semconv.USAGE_OUTPUT_TOKENS] == call.output_tokens
    assert out[semconv.RESPONSE_FINISH_REASONS] == call.finish_reasons
    assert out.get(semconv.RESPONSE_MODEL) == call.response_model
    assert (semconv.REQUEST_TEMPERATURE in out) is (call.temperature is not None)
    assert (semconv.REQUEST_MAX_TOKENS in out) is (call.max_tokens is not None)
    assert (semconv.ERROR_TYPE in out) is (call.error_type is not None)
    assert ("app.ttft_ms" in out) is (call.ttft_ms is not None)
    assert ("app.cost.pricing_version" in out) is (call.cost is not None)
    assert ("app.cost.eur" in out) is (call.cost is not None)
