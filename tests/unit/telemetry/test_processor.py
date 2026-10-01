"""R1 in isolation: a bounded span queue that never blocks the request path and counts everything it loses.

The exporters here are fakes on purpose. What is under test is the queue's promise, which must hold for ANY
exporter: `on_end` returns at once whatever the exporter is doing, and every span that does not reach the
store is in `dropped` — whether it never fit in the queue or the store refused it. The real store, killed
mid-test, is level 2 (tests/integration, `make test-int -k degradation`).
"""

import threading
import time
from collections.abc import Sequence

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import ReadableSpan, TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

from evalgate.telemetry.processor import DROPPED_METRIC, BoundedSpanProcessor, register_dropped_counter


class Recording(SpanExporter):
    def __init__(self, result: SpanExportResult = SpanExportResult.SUCCESS) -> None:
        self.result = result
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.spans.extend(spans)
        return self.result


class Stuck(SpanExporter):
    """A store that hangs: the worker blocks inside `export` until the test lets it go."""

    def __init__(self) -> None:
        self.entered = threading.Event()
        self.release = threading.Event()
        self.spans: list[ReadableSpan] = []

    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        self.entered.set()
        self.release.wait(timeout=5)
        self.spans.extend(spans)
        return SpanExportResult.SUCCESS


class Raising(SpanExporter):
    def export(self, spans: Sequence[ReadableSpan]) -> SpanExportResult:
        raise ConnectionRefusedError(f"clickhouse is down, {len(spans)} spans lost")


def traced(processor: BoundedSpanProcessor, n: int) -> None:
    provider = TracerProvider()
    provider.add_span_processor(processor)
    tracer = provider.get_tracer("test")
    for i in range(n):
        tracer.start_span(f"span {i}").end()


def test_every_span_reaches_a_healthy_store_and_none_is_dropped() -> None:
    store = Recording()
    processor = BoundedSpanProcessor(store, capacity=64, batch_size=8)

    traced(processor, 50)
    assert processor.force_flush()

    assert (len(store.spans), processor.exported, processor.dropped) == (50, 50, 0)
    processor.shutdown()


def test_a_full_queue_drops_counts_and_never_waits() -> None:
    store = Stuck()
    processor = BoundedSpanProcessor(store, capacity=4, batch_size=1)
    traced(processor, 1)
    assert store.entered.wait(timeout=5), "the worker should be inside export, holding one span"

    started = time.perf_counter()
    traced(processor, 10)  # 4 fit in the queue, 6 do not
    elapsed = time.perf_counter() - started

    assert processor.dropped == 6
    # Generous bound: it is the order of magnitude that matters. Waiting for the store would be 5 s.
    assert elapsed < 0.5
    store.release.set()
    assert processor.force_flush()
    assert (processor.exported, processor.dropped) == (5, 6)
    processor.shutdown()


@pytest.mark.parametrize("store", [Recording(SpanExportResult.FAILURE), Raising()])
def test_a_store_that_refuses_counts_the_whole_batch_as_dropped(store: SpanExporter) -> None:
    processor = BoundedSpanProcessor(store, capacity=64, batch_size=8)

    traced(processor, 20)
    processor.force_flush()

    assert (processor.exported, processor.dropped) == (0, 20)
    processor.shutdown()


def test_a_batch_that_never_fills_still_leaves_after_the_flush_interval() -> None:
    """At 1 rps and batches of 100, spans would otherwise sit in memory for minutes, lost on a crash."""
    store = Recording()
    processor = BoundedSpanProcessor(store, capacity=64, batch_size=100, flush_interval_s=0.1)

    traced(processor, 3)
    deadline = time.monotonic() + 5
    while len(store.spans) < 3 and time.monotonic() < deadline:
        time.sleep(0.01)

    assert (len(store.spans), processor.dropped) == (3, 0)
    processor.shutdown()


def test_after_shutdown_spans_are_dropped_and_counted_not_silently_ignored() -> None:
    processor = BoundedSpanProcessor(Recording(), capacity=64, batch_size=8)
    processor.shutdown()

    traced(processor, 3)

    assert processor.dropped == 3


def test_shutdown_exports_what_was_already_queued() -> None:
    store = Recording()
    processor = BoundedSpanProcessor(store, capacity=64, batch_size=64, flush_interval_s=60)

    traced(processor, 5)
    processor.shutdown()

    assert (len(store.spans), processor.dropped) == (5, 0)


def test_the_dropped_counter_is_published_under_its_contract_name() -> None:
    processor = BoundedSpanProcessor(Recording(SpanExportResult.FAILURE), capacity=64, batch_size=8)
    reader = InMemoryMetricReader()
    register_dropped_counter(MeterProvider(metric_readers=[reader]).get_meter("evalgate"), processor)

    traced(processor, 7)
    processor.force_flush()

    data = reader.get_metrics_data()
    assert data is not None
    (metric,) = [m for rm in data.resource_metrics for sm in rm.scope_metrics for m in sm.metrics]
    assert (metric.name, metric.unit) == (DROPPED_METRIC, "{span}")
    assert [point.value for point in metric.data.data_points] == [7]
    processor.shutdown()
