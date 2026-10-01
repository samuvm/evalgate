"""Span exporter to ClickHouse, straight into `otel_traces` (ADR-012). I/O only: the row is `rows.row_of`.

Its promise to the bounded queue (telemetry/processor.py) is a RESULT: SUCCESS when the insert returned,
FAILURE otherwise. Whatever the store does, it never raises into the worker and it never returns SUCCESS for
spans that were not written, which is what keeps `app.spans.dropped` honest with ClickHouse down.
The client is built LAZILY, by the `connect` it is handed (cli/main.py, with short timeouts): ClickHouse down
when the proxy starts cannot stop the proxy from starting, and a server that restarts mid-run is reconnected
on the next batch. Until then every batch is a FAILURE, counted as dropped; the request never notices (R1).
"""

from collections.abc import Callable, Sequence

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from evalgate.telemetry.exporters import StoreClient
from evalgate.telemetry.rows import COLUMNS, TRACES_TABLE, row_of


class ClickHouseSpanExporter(SpanExporter):
    def __init__(self, connect: Callable[[], StoreClient], table: str = TRACES_TABLE) -> None:
        self._connect = connect
        self._client: StoreClient | None = None
        self._table = table

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        try:
            if self._client is None:
                self._client = self._connect()
            self._client.insert(self._table, [row_of(span) for span in spans], column_names=COLUMNS)
        except Exception:  # a lost batch, counted by the queue; never an exception into its worker
            self._client = None  # whatever broke, the next batch starts from a fresh connection
            return SpanExportResult.FAILURE
        return SpanExportResult.SUCCESS

    def shutdown(self) -> None:
        if self._client is not None:
            self._client.close()
