"""The trace pipeline, assembled once: `LlmCall` → span → bounded queue → exporter.

`evalgate serve` builds it and the level-2 tests build the SAME one, so what G-TRACE-0 and G-TRACE-DEGRADE
measure is what runs. The proxy only ever sees `sink` (R1).
"""

from collections.abc import Callable
from dataclasses import dataclass

from opentelemetry.metrics import Meter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SpanExporter

from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.processor import BoundedSpanProcessor, register_dropped_counter
from evalgate.telemetry.translate import emit_span


@dataclass(frozen=True, slots=True)
class TracePipeline:
    sink: Callable[[LlmCall], None]  # what ProxySettings.on_call receives
    processor: BoundedSpanProcessor  # its counters: exported / dropped

    def shutdown(self) -> None:
        self.processor.shutdown()


def build_pipeline(  # noqa: PLR0913 - the pipeline's knobs, all keyword-only and all named at the call
    exporter: SpanExporter,
    *,
    capacity: int,
    batch_size: int,
    flush_interval_s: float,
    service_name: str,
    meter: Meter | None = None,
) -> TracePipeline:
    processor = BoundedSpanProcessor(
        exporter, capacity=capacity, batch_size=batch_size, flush_interval_s=flush_interval_s
    )
    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    provider.add_span_processor(processor)
    if meter is not None:
        register_dropped_counter(meter, processor)
    tracer = provider.get_tracer("evalgate")

    def sink(call: LlmCall) -> None:
        emit_span(tracer, call)

    return TracePipeline(sink, processor)
