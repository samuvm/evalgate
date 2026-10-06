"""F4 at the mounting: the trace of a served call carries what it cost and WHICH TABLE priced it.

G-OTEL-CONTRACT names `app.cost.pricing_version` on purpose (docs/GOALS.yaml): without the table's date a
cost in a trace cannot be recomputed, and a cost that cannot be recomputed is an anecdote. And the other
half: with no table published the trace says nothing about cost, which reads "unpriced", never "free".
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import httpx
from fastapi.testclient import TestClient

from evalgate.pricing.model import Fx, ModelPrice, PriceTable
from evalgate.proxy.app import ProxySettings, create_app
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.translate import attributes

from ._proxy import UPSTREAM, Upstream

ASKED = b'{"model":"qwen3.5:4b-mlx","messages":[{"role":"user","content":"precio?"}]}'
ANSWER = (
    b'{"id":"c1","object":"chat.completion","created":1,"model":"qwen3.5:4b-mlx","choices":[{"index":0,'
    b'"message":{"role":"assistant","content":"42"},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":1500,"completion_tokens":500,"total_tokens":2000}}'
)
AUGUST = PriceTable(
    date(2026, 8, 1),
    {"qwen3.5:4b-mlx": ModelPrice(Decimal("0.0008"), Decimal("0.004"))},
    "USD",
    Fx(Decimal("0.92"), date(2026, 8, 8)),
)
MID_AUGUST_NS = int(datetime(2026, 8, 15, 12, tzinfo=UTC).timestamp()) * 1_000_000_000


def served(tables: list[PriceTable]) -> LlmCall:
    calls: list[LlmCall] = []
    settings = ProxySettings(
        upstream_base_url=UPSTREAM, on_call=calls.append, price_tables=tables, clock=lambda: MID_AUGUST_NS
    )
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(Upstream(body=ANSWER).handler))
    response = TestClient(create_app(settings, client=upstream)).post("/v1/chat/completions", content=ASKED)
    assert response.status_code == 200
    (call,) = calls
    return call


def test_a_served_call_is_traced_with_its_cost_and_the_version_of_the_table() -> None:
    span = attributes(served([AUGUST]))

    # 1.5 x 0.0008 + 0.5 x 0.004 = 0.0032 USD; x 0.92 = 0.002944 EUR
    assert span["app.cost.eur"] == 0.002944
    assert span["app.cost.pricing_version"] == "2026-08-01"


def test_with_no_table_published_the_trace_says_nothing_about_cost() -> None:
    span = attributes(served([]))

    assert "app.cost.eur" not in span
    assert "app.cost.pricing_version" not in span
