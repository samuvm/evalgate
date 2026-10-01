"""The store for real: our migrations build `otel_traces`, and a span written by the exporter comes back."""

from typing import Any

from evalgate.telemetry.exporters.clickhouse import ClickHouseSpanExporter
from evalgate.telemetry.migrations import apply
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.pipeline import build_pipeline

from .conftest import Store

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
    started_ns=1_789_045_001_123_456_789,
    ended_ns=1_789_045_001_373_456_789,
    client_disconnected=True,
    temperature=0.0,
)


def test_migrations_are_idempotent_and_recorded(store: Store) -> None:
    client: Any = store.connect()
    try:
        assert apply(client) == []  # the fixture already ran them
        ledger = client.query("SELECT version, sha256 FROM schema_migrations ORDER BY version").result_rows
    finally:
        client.close()
    assert [version for version, _ in ledger] == ["0001"]


def test_a_span_comes_back_from_clickhouse_as_it_was_written(store: Store) -> None:
    pipeline = build_pipeline(
        ClickHouseSpanExporter(store.connect),
        capacity=8,
        batch_size=8,
        flush_interval_s=0.1,
        service_name="evalgate-roundtrip",
    )
    pipeline.sink(CALL)
    assert pipeline.processor.force_flush()
    pipeline.shutdown()

    client: Any = store.connect()
    try:
        (row,) = client.query(
            "SELECT toUnixTimestamp64Nano(Timestamp), Duration, SpanName, SpanKind, StatusCode,"
            " SpanAttributes FROM otel_traces WHERE ServiceName = 'evalgate-roundtrip'"
        ).result_rows
    finally:
        client.close()
    timestamp, duration, name, kind, status, attributes = row
    assert (timestamp, duration) == (CALL.started_ns, CALL.ended_ns - CALL.started_ns)  # nanoseconds, exact
    assert (name, kind, status) == ("chat qwen3.5:4b-mlx", "Client", "Unset")
    assert attributes["gen_ai.usage.output_tokens"] == "4"
    assert attributes["gen_ai.request.temperature"] == "0.0"
    assert attributes["app.stream.client_disconnected"] == "true"
    assert (pipeline.processor.exported, pipeline.processor.dropped) == (1, 0)
