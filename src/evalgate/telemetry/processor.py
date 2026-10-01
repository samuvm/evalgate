"""Bounded span processor: the hand-off between the request path and the store. R1.

**No trace may take a request down or slow it down.** The request thread only does `put_nowait` into a
queue of fixed capacity; a worker thread drains it in batches towards the exporter. When the store is slow
or down, the worker blocks, the queue fills up, and from then on every new span is dropped AT ONCE and
counted. The request never waits for the store: that is the whole design.

Why not the SDK's `BatchSpanProcessor`, which also has a bounded queue: it ignores the result of
`export()`. A store that answers `FAILURE` loses the batch without anybody counting it, so
`app.spans.dropped` would say 0 with ClickHouse down, which is the exact case the counter exists for
(contract otel-genai §4: "un descarte silencioso es peor que un descarte medido"). Here a span is either
`exported` (the store said SUCCESS) or `dropped` (it did not fit, the store refused it, or the processor
was already shut down). Nothing else can happen to it, and G-TRACE-0 / G-TRACE-DEGRADE read those two.

Batches, and not one insert per span, because the store is ClickHouse: many tiny inserts are the classic
way to make it suffer (one part per insert). A batch leaves when it is full or `flush_interval_s` after its
first span, whichever comes first.
"""

import queue
import threading
import time
from collections.abc import Iterable

from opentelemetry.metrics import CallbackOptions, Meter, Observation
from opentelemetry.sdk.trace import ReadableSpan, SpanProcessor
from opentelemetry.sdk.trace.export import SpanExporter, SpanExportResult

DROPPED_METRIC = "app.spans.dropped"  # contract otel-genai §4: ours, so `app.*`, a counter in `{span}`
_POLL_S = 0.05  # how long the worker may be deaf to a shutdown or a flush; never seen by a request


class BoundedSpanProcessor(SpanProcessor):
    def __init__(
        self, exporter: SpanExporter, capacity: int, batch_size: int, flush_interval_s: float = 1.0
    ) -> None:
        self._exporter = exporter
        self._batch_size = batch_size
        self._flush_interval_s = flush_interval_s
        self._queue: queue.Queue[ReadableSpan] = queue.Queue(maxsize=capacity)
        self._lock = threading.Lock()
        self._settled = threading.Condition(self._lock)
        self._pending = 0  # accepted into the queue and not yet exported nor dropped
        self._dropped = 0
        self._exported = 0
        self._stopping = threading.Event()
        self._hurry = (
            threading.Event()
        )  # a flush was asked for: ship the batch without waiting for it to fill
        self._worker = threading.Thread(target=self._drain, name="evalgate-span-export", daemon=True)
        self._worker.start()

    @property
    def dropped(self) -> int:
        with self._lock:
            return self._dropped

    @property
    def exported(self) -> int:
        with self._lock:
            return self._exported

    def on_end(self, span: ReadableSpan) -> None:
        """Runs on the REQUEST path. Constant time, no wait, no exception: it enqueues or it counts."""
        if self._stopping.is_set():
            self._count(dropped=1)
            return
        with self._lock:
            try:
                self._queue.put_nowait(span)
            except queue.Full:
                self._dropped += 1
            else:
                self._pending += 1

    def force_flush(self, timeout_millis: int = 30_000) -> bool:
        """Ship now and wait until every accepted span is exported or dropped. Tests and shutdown only."""
        self._hurry.set()
        try:
            with self._settled:
                return self._settled.wait_for(lambda: self._pending == 0, timeout=timeout_millis / 1000)
        finally:
            self._hurry.clear()

    def shutdown(self) -> None:
        """Stop accepting, export what is already queued, then close the exporter."""
        self._stopping.set()
        self._worker.join()
        self._exporter.shutdown()

    def _drain(self) -> None:
        while not (self._stopping.is_set() and self._queue.empty()):
            batch = self._next_batch()
            if batch:
                self._export(batch)

    def _next_batch(self) -> list[ReadableSpan]:
        batch: list[ReadableSpan] = []
        deadline: float | None = None
        while len(batch) < self._batch_size:
            try:
                batch.append(self._queue.get(timeout=_POLL_S))
            except queue.Empty:
                if self._stopping.is_set() or self._hurry.is_set() or self._expired(deadline):
                    break
                continue
            if deadline is None:
                deadline = time.monotonic() + self._flush_interval_s
            if self._expired(deadline):
                break
        return batch

    @staticmethod
    def _expired(deadline: float | None) -> bool:
        return deadline is not None and time.monotonic() >= deadline

    def _export(self, batch: list[ReadableSpan]) -> None:
        try:
            ok = self._exporter.export(batch) is SpanExportResult.SUCCESS
        except Exception:  # whatever the store does, it is a lost batch, never a dead worker
            ok = False
        self._count(exported=len(batch) if ok else 0, dropped=0 if ok else len(batch), settled=len(batch))

    def _count(self, exported: int = 0, dropped: int = 0, settled: int = 0) -> None:
        with self._settled:
            self._exported += exported
            self._dropped += dropped
            self._pending -= settled
            self._settled.notify_all()


def register_dropped_counter(meter: Meter, processor: BoundedSpanProcessor) -> None:
    """Publish `app.spans.dropped` as a monotonic counter read from the processor at collection time."""

    def observe(_options: CallbackOptions) -> Iterable[Observation]:
        return [Observation(processor.dropped)]

    meter.create_observable_counter(
        DROPPED_METRIC,
        callbacks=[observe],
        unit="{span}",
        description="Spans that never reached the store: queue full, store refused, or processor shut down",
    )
