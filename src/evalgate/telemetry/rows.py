"""A finished span as one row of `otel_traces`, the table layout of the Collector's `clickhouseexporter`.

Same table name, same columns, same text encoding of attribute values. The store is written directly from the
proxy (ADR-012: with the Collector in between, the proxy would get SUCCESS while ClickHouse is down and
`app.spans.dropped` would measure nothing), but a query or a panel written against spans stored by the
Collector works unchanged against these. Moving to the Collector later is configuration, not a migration.

Pure: no client, no I/O. `telemetry/exporters/clickhouse.py` does the insert.
"""

import json
from collections.abc import Mapping
from typing import Any

from opentelemetry.sdk.trace import ReadableSpan
from opentelemetry.util.types import AttributeValue

TRACES_TABLE = "otel_traces"
COLUMNS = (
    "Timestamp",
    "TraceId",
    "SpanId",
    "ParentSpanId",
    "TraceState",
    "SpanName",
    "SpanKind",
    "ServiceName",
    "ResourceAttributes",
    "ScopeName",
    "ScopeVersion",
    "SpanAttributes",
    "Duration",
    "StatusCode",
    "StatusMessage",
)


def attribute_text(value: AttributeValue) -> str:
    """How the Collector writes a value into `Map(String, String)`: lists as JSON, booleans in lower case."""
    if isinstance(value, bool):  # before `int`: in Python a bool IS an int
        return "true" if value else "false"
    if isinstance(value, str):
        return value
    if isinstance(value, int | float):
        return repr(value)
    return json.dumps(list(value), ensure_ascii=False, separators=(",", ":"))


def _texts(attributes: Mapping[str, AttributeValue] | None) -> dict[str, str]:
    return {key: attribute_text(value) for key, value in (attributes or {}).items()}


def row_of(span: ReadableSpan) -> tuple[Any, ...]:
    """One value per column of `COLUMNS`, in that order. Times stay in integer nanoseconds: exact."""
    context = span.get_span_context()
    start, end = span.start_time or 0, span.end_time or 0
    scope = span.instrumentation_scope
    return (
        start,
        format(context.trace_id, "032x") if context else "",
        format(context.span_id, "016x") if context else "",
        format(span.parent.span_id, "016x") if span.parent else "",
        context.trace_state.to_header() if context else "",
        span.name,
        span.kind.name.capitalize(),  # CLIENT → "Client", as pdata spells it
        str(span.resource.attributes.get("service.name", "")),
        _texts(span.resource.attributes),
        scope.name if scope else "",
        (scope.version or "") if scope else "",
        _texts(span.attributes),
        end - start,
        span.status.status_code.name.capitalize(),  # UNSET → "Unset", ERROR → "Error"
        span.status.description or "",
    )
