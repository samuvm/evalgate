"""Exporters: the I/O end of the telemetry pipeline. `proxy/` never imports from here (R1, rule)."""

from collections.abc import Sequence
from typing import Any, Protocol


class StoreClient(Protocol):
    """The part of a `clickhouse_connect` client that the migrations and the exporter use. A type, not code:
    it lives here, with the I/O, and not in a testable module where G-FUNC-COV would count its stubs."""

    def command(self, cmd: str) -> Any: ...
    def query(self, sql: str) -> Any: ...
    def insert(self, table: str, data: Sequence[Sequence[Any]], column_names: Sequence[str]) -> Any: ...
    def close(self) -> None: ...
