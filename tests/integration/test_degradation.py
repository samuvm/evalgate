"""G-TRACE-DEGRADE: ClickHouse dies MID-TEST and the proxy does not notice (contract otel-genai §6: "se
prueba tumbando el contenedor a mitad del test, no razonándolo").

Two phases at the same sustained rate, same pipeline, same process:
1. store healthy: the p95 of reference, and the rows in ClickHouse match what the queue says it exported;
2. `docker kill` (not stop: a dying store does not say goodbye) fired while traffic flows, on request 50.

What must hold, from GOALS.yaml: every request served (ratio 1.0), the p95 of phase 2 no more than the
threshold above phase 1, and no silent loss: every span emitted ends up exported or counted in
`app.spans.dropped`. The artefact goes to evals/reports/degradation-<date>.json, which the goal reads.
"""

import asyncio
import json
import platform
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import yaml

from evalgate.telemetry.exporters.clickhouse import ClickHouseSpanExporter
from evalgate.telemetry.pipeline import build_pipeline

from ._load import p95, serve
from .conftest import Store

GOAL = "G-TRACE-DEGRADE"
ROOT = Path(__file__).resolve().parents[2]
UMBRAL: dict[str, Any] = next(
    m for m in yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text("utf-8"))["metas"] if m["id"] == GOAL
)["umbral"]
SERVED_RATIO: float = UMBRAL["adicionales"][0]["valor"]
RPS, PER_PHASE, KILL_AT = 50, 1000, 50  # 20 s per phase; the kill lands inside phase 2, with traffic flowing
CAPACITY, BATCH, FLUSH_S = 4096, 512, 1.0  # production knobs (cli/main.py)


def test_degradation_with_the_store_killed_mid_test(store: Store) -> None:
    service = f"evalgate-degrade-{uuid.uuid4().hex[:8]}"
    pipeline = build_pipeline(
        ClickHouseSpanExporter(store.connect),
        capacity=CAPACITY,
        batch_size=BATCH,
        flush_interval_s=FLUSH_S,
        service_name=service,
    )

    healthy = asyncio.run(serve(pipeline.sink, RPS, PER_PHASE))
    assert pipeline.processor.force_flush()
    persisted, exported_healthy = store.count(service), pipeline.processor.exported

    async def kill() -> None:
        await asyncio.to_thread(store.kill)

    killed = asyncio.run(serve(pipeline.sink, RPS, PER_PHASE, at={KILL_AT: kill}))
    assert pipeline.processor.force_flush(timeout_millis=120_000)
    pipeline.shutdown()

    emitted = healthy.ok + killed.ok
    served_ratio = emitted / (2 * PER_PHASE)
    delta_ms = p95(killed.latencies_ms) - p95(healthy.latencies_ms)
    exported, dropped = pipeline.processor.exported, pipeline.processor.dropped
    report = {
        "goal": GOAL,
        "p95_delta_ms": round(delta_ms, 3),
        "p95_healthy_ms": round(p95(healthy.latencies_ms), 3),
        "p95_killed_ms": round(p95(killed.latencies_ms), 3),
        "served_ratio": served_ratio,
        "n_per_phase": PER_PHASE,
        "rps": RPS,
        "kill_at_request": KILL_AT,
        "spans_emitted": emitted,
        "spans_exported": exported,
        "spans_dropped": dropped,
        "rows_before_kill": persisted,
        "queue": {"capacity": CAPACITY, "batch_size": BATCH, "flush_interval_s": FLUSH_S},
        "hardware": {
            "machine": platform.machine(),
            "system": platform.platform(),
            "python": platform.python_version(),
        },
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    out = ROOT / "evals" / "reports" / f"degradation-{datetime.now(UTC).date().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    assert served_ratio == SERVED_RATIO
    assert persisted == exported_healthy == PER_PHASE, "phase 1: the rows are the evidence of the counter"
    assert exported + dropped == emitted, "a span is exported or counted as dropped: no third way out"
    assert dropped > 0, "the store died: if nothing was dropped, the kill did not happen where it should"
    assert delta_ms <= UMBRAL["valor"]
