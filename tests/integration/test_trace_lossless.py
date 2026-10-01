"""G-TRACE-0: zero spans lost with a healthy store, at a declared sustained rate.

Lost = requests served - spans persisted, counted IN ClickHouse, not in our own counters: a counter that says
"exported" is the claim, the row is the evidence. The rate and the duration are the goal's own definition
(GOALS.yaml nota: 50 rps sustained for 120 s); the README publishes the rate next to the number, because
"0 % loss" without the load it was measured at says nothing.
"""

import asyncio
import uuid
from pathlib import Path
from typing import Any

import yaml
from tests._meter import Meter

from evalgate.telemetry.exporters.clickhouse import ClickHouseSpanExporter
from evalgate.telemetry.pipeline import build_pipeline

from ._load import serve
from .conftest import Store

GOAL = "G-TRACE-0"
ROOT = Path(__file__).resolve().parents[2]
UMBRAL: dict[str, Any] = next(
    m for m in yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text("utf-8"))["metas"] if m["id"] == GOAL
)["umbral"]
RPS, SECONDS = 50, 120  # carga declarada por la meta, no un umbral
# The production knobs of `evalgate serve` (cli/main.py): the pipeline measured is the one that runs.
CAPACITY, BATCH, FLUSH_S = 4096, 512, 1.0


def test_trace_lossless_at_the_declared_sustained_rate(store: Store, meter: Meter) -> None:
    service = f"evalgate-lossless-{uuid.uuid4().hex[:8]}"
    pipeline = build_pipeline(
        ClickHouseSpanExporter(store.connect),
        capacity=CAPACITY,
        batch_size=BATCH,
        flush_interval_s=FLUSH_S,
        service_name=service,
    )

    served = asyncio.run(serve(pipeline.sink, RPS, RPS * SECONDS))
    assert pipeline.processor.force_flush()
    pipeline.shutdown()

    persisted = store.count(service)
    lost = served.ok - persisted
    meter.observe(GOAL, "perdidos", lost)
    meter.observe(GOAL, "servidas", served.ok)
    meter.observe(GOAL, "rps", RPS)
    assert served.ok == RPS * SECONDS, "every request is served: a lost request is not a lost span"
    assert lost == UMBRAL["valor"]
    assert (pipeline.processor.dropped, pipeline.processor.exported) == (0, persisted)
