"""The ClickHouse store, without ClickHouse: span → row, which migrations are pending, and the exporter's
promise to the bounded queue (SUCCESS or FAILURE, never an exception, never a hang it could avoid).

The client is a fake that records what it was asked. The real server, and killing it mid-test, is level 2
(tests/integration/test_clickhouse_store.py).
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evalgate.telemetry.exporters.clickhouse import ClickHouseSpanExporter
from evalgate.telemetry.migrations import (
    MIGRATIONS,
    Migration,
    MigrationTampered,
    apply,
    available,
    pending,
)
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.rows import COLUMNS, TRACES_TABLE, attribute_text, row_of
from evalgate.telemetry.translate import emit_span

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
)


def finished(service: str = "evalgate") -> ReadableSpan:
    store = InMemorySpanExporter()
    provider = TracerProvider(resource=Resource.create({"service.name": service}))
    provider.add_span_processor(SimpleSpanProcessor(store))
    emit_span(provider.get_tracer("evalgate", "0.3.0"), CALL)
    (span,) = store.get_finished_spans()
    return span


# --- span → fila del esquema otel_traces --------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "text"),
    [
        ("qwen", "qwen"),
        (15, "15"),
        (0.1, "0.1"),
        (True, "true"),
        (False, "false"),
        (("stop", "length"), '["stop","length"]'),
        ((), "[]"),
    ],
)
def test_attribute_values_are_written_as_the_collector_writes_them(value: Any, text: str) -> None:
    """Map(String, String), like clickhouseexporter: JSON for lists, lower-case booleans. A query written
    against spans stored by the Collector has to work unchanged against ours."""
    assert attribute_text(value) == text


def test_a_row_has_one_value_per_column_in_column_order() -> None:
    row = dict(zip(COLUMNS, row_of(finished()), strict=True))

    assert row["Timestamp"] == CALL.started_ns
    assert row["Duration"] == CALL.ended_ns - CALL.started_ns
    assert (row["SpanName"], row["SpanKind"], row["StatusCode"]) == ("chat qwen3.5:4b-mlx", "Client", "Unset")
    assert row["ServiceName"] == "evalgate"
    assert (row["ScopeName"], row["ScopeVersion"]) == ("evalgate", "0.3.0")
    assert (len(row["TraceId"]), len(row["SpanId"])) == (32, 16)
    assert row["ParentSpanId"] == ""
    assert row["SpanAttributes"]["gen_ai.usage.input_tokens"] == "15"
    assert json.loads(row["SpanAttributes"]["gen_ai.response.finish_reasons"]) == ["stop"]
    assert row["SpanAttributes"]["app.stream.client_disconnected"] == "true"
    assert TRACES_TABLE == "otel_traces"


# --- migraciones: inmutables como las tablas de precios ------------------------------------------------


def test_the_packaged_migrations_are_numbered_without_gaps() -> None:
    versions = [m.version for m in available(MIGRATIONS)]

    assert versions == [f"{n:04d}" for n in range(1, len(versions) + 1)]
    assert versions, "at least the otel_traces table"


def test_pending_skips_what_was_applied_with_the_same_digest() -> None:
    first, second = Migration("0001", "a", "sql a"), Migration("0002", "b", "sql b")

    assert pending({"0001": first.sha256}, [first, second]) == [second]


def test_a_migration_edited_after_being_applied_stops_everything() -> None:
    """Same rule as pricing (R4): what was applied is history. A fix is a NEW migration."""
    applied = Migration("0001", "a", "sql a")
    edited = Migration("0001", "a", "sql a -- retocada")

    with pytest.raises(MigrationTampered, match="0001"):
        pending({"0001": applied.sha256}, [edited])


@dataclass
class FakeClient:
    applied: dict[str, str] = field(default_factory=dict)
    commands: list[str] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    inserts: list[tuple[str, list[Any], tuple[str, ...]]] = field(default_factory=list)
    fail: BaseException | None = None
    closed: bool = False

    def command(self, cmd: str) -> None:
        self.commands.append(cmd)

    def query(self, sql: str) -> Any:
        self.queries.append(sql)
        return type("R", (), {"result_rows": sorted(self.applied.items())})()

    def insert(self, table: str, data: list[Any], column_names: tuple[str, ...]) -> None:
        if self.fail is not None:
            raise self.fail
        self.inserts.append((table, data, column_names))
        if table == "schema_migrations":
            self.applied.update({row[0]: row[2] for row in data})

    def close(self) -> None:
        self.closed = True


def test_apply_runs_each_pending_statement_once_and_records_it(tmp_path: Path) -> None:
    (tmp_path / "0001_first.sql").write_text("CREATE TABLE a (x UInt8) ENGINE = Memory;\n", "utf-8")
    (tmp_path / "0002_second.sql").write_text("CREATE TABLE b (x UInt8) ENGINE = Memory;\n", "utf-8")
    client = FakeClient()

    assert [m.version for m in apply(client, tmp_path)] == ["0001", "0002"]
    assert apply(client, tmp_path) == []  # idempotent: the second run finds nothing to do

    created = [c for c in client.commands if c.startswith("CREATE TABLE a") or c.startswith("CREATE TABLE b")]
    assert len(created) == 2
    assert set(client.applied) == {"0001", "0002"}


# --- el exportador: la promesa que hace a la cola -------------------------------------------------------


def test_export_inserts_the_batch_into_otel_traces() -> None:
    client = FakeClient()

    result = ClickHouseSpanExporter(lambda: client).export([finished(), finished()])

    assert result is SpanExportResult.SUCCESS
    ((table, rows, columns),) = client.inserts
    assert (table, len(rows), columns) == (TRACES_TABLE, 2, COLUMNS)


def test_a_store_that_fails_is_a_failure_result_not_an_exception() -> None:
    """The bounded queue counts FAILURE as dropped. An exception would also be counted, but the exporter's
    contract with any SpanProcessor is a result, and the SDK's own processors do not catch everything."""
    client = FakeClient(fail=ConnectionRefusedError("clickhouse down"))

    assert ClickHouseSpanExporter(lambda: client).export([finished()]) is SpanExportResult.FAILURE


def test_a_store_down_at_start_does_not_stop_anything_and_is_reconnected_later() -> None:
    """ClickHouse down when the proxy starts: the first batch fails (counted as dropped by the queue), and
    the next one connects again instead of reusing a dead client forever."""
    client = FakeClient()
    attempts: list[int] = []

    def connect() -> FakeClient:
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionRefusedError("clickhouse not up yet")
        return client

    exporter = ClickHouseSpanExporter(connect)

    assert exporter.export([finished()]) is SpanExportResult.FAILURE
    assert exporter.export([finished()]) is SpanExportResult.SUCCESS
    assert (len(attempts), len(client.inserts)) == (2, 1)


def test_a_failed_insert_drops_the_connection_for_the_next_batch() -> None:
    broken, fresh = FakeClient(fail=ConnectionResetError("reset")), FakeClient()
    clients = iter([broken, fresh])
    exporter = ClickHouseSpanExporter(lambda: next(clients))

    assert exporter.export([finished()]) is SpanExportResult.FAILURE
    assert exporter.export([finished()]) is SpanExportResult.SUCCESS
    assert len(fresh.inserts) == 1


def test_shutdown_closes_the_client_it_opened_and_opens_none() -> None:
    client = FakeClient()
    exporter = ClickHouseSpanExporter(lambda: client)

    exporter.shutdown()
    assert not client.closed  # never connected: nothing to close, and no connection opened just to close it

    exporter.export([finished()])
    exporter.shutdown()
    assert client.closed
