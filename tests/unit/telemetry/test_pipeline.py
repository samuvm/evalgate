"""The assembled pipeline: a call handed to `sink` comes out of the exporter as one span, counted."""

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.pipeline import build_pipeline

CALL = LlmCall(
    operation="chat",
    provider="ollama",
    server_address="localhost",
    request_model="m",
    response_model="m",
    input_tokens=3,
    output_tokens=2,
    usage_source="provider",
    finish_reasons=("stop",),
    started_ns=1_000,
    ended_ns=2_000,
)


def test_a_call_handed_to_the_sink_reaches_the_exporter_as_one_span_of_its_service() -> None:
    store = InMemorySpanExporter()
    reader = InMemoryMetricReader()
    pipeline = build_pipeline(
        store,
        capacity=8,
        batch_size=4,
        flush_interval_s=0.1,
        service_name="evalgate-test",
        meter=MeterProvider(metric_readers=[reader]).get_meter("t"),
    )

    pipeline.sink(CALL)
    pipeline.shutdown()

    (span,) = store.get_finished_spans()
    assert span.resource.attributes["service.name"] == "evalgate-test"
    assert (pipeline.processor.exported, pipeline.processor.dropped) == (1, 0)
    assert reader.get_metrics_data() is not None
