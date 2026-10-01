"""Hypothesis strategy for `LlmCall`, shared by the contract test (G-OTEL-CONTRACT) and the property test.

It lives next to `_meter.py` because two suites need the same generator: if each had its own, the goal
would be measured over one population and the totality property over another.
"""

from decimal import Decimal

from hypothesis import strategies as st

from evalgate.telemetry.model import Cost, LlmCall

_text = st.text(st.characters(codec="utf-8", exclude_categories=("Cs",)), min_size=1, max_size=40)
_tokens = st.integers(min_value=0, max_value=2_000_000)


@st.composite
def llm_calls(draw: st.DrawFn) -> LlmCall:
    started = draw(st.integers(min_value=1, max_value=4_000_000_000_000_000_000))
    return LlmCall(
        operation=draw(st.sampled_from(["chat", "text_completion", "embeddings"])),
        provider=draw(st.sampled_from(["ollama", "openai", "aws.bedrock"]) | _text),
        server_address=draw(st.sampled_from(["localhost", "127.0.0.1", "api.openai.com"]) | _text),
        request_model=draw(_text),
        response_model=draw(st.none() | _text),
        input_tokens=draw(_tokens),
        output_tokens=draw(_tokens),
        usage_source=draw(st.sampled_from(["provider", "estimated"])),
        finish_reasons=tuple(draw(st.lists(_text, max_size=3))),
        started_ns=started,
        ended_ns=started + draw(st.integers(min_value=0, max_value=600_000_000_000)),
        client_disconnected=draw(st.booleans()),
        temperature=draw(st.none() | st.floats(min_value=0, max_value=2, allow_nan=False)),
        max_tokens=draw(st.none() | st.integers(min_value=1, max_value=1_000_000)),
        error_type=draw(st.none() | st.sampled_from(["timeout", "upstream_error", "500"])),
        ttft_ms=draw(st.none() | st.floats(min_value=0, max_value=600_000, allow_nan=False)),
        cost=draw(
            st.none()
            | st.builds(
                Cost,
                eur=st.decimals(min_value=Decimal(0), max_value=Decimal(1000), places=6),
                pricing_version=st.dates().map(lambda d: d.isoformat()),
            )
        ),
    )
