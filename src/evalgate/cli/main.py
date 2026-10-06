"""`evalgate` CLI. Wiring only: excluded from unit tests (RULES §2), covered by e2e and integration.

This is where the trace pipeline is assembled, and the only place that sees both ends of it: the proxy gets a
plain `on_call` sink and never an exporter (R1, `scripts/rules/no_blocking_export.py`).
"""

from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Annotated

import clickhouse_connect
import typer
import uvicorn
from opentelemetry import metrics

from evalgate.cli import compare as compare_cli
from evalgate.cli import pricing_repro
from evalgate.gate.decision import BLOCK
from evalgate.pricing.loader import load_tables
from evalgate.proxy.app import DEFAULT_PROVIDER, DEFAULT_UPSTREAM, ProxySettings, create_app
from evalgate.telemetry.exporters import StoreClient
from evalgate.telemetry.exporters.clickhouse import ClickHouseSpanExporter
from evalgate.telemetry.migrations import apply
from evalgate.telemetry.model import LlmCall
from evalgate.telemetry.pipeline import build_pipeline

# 4096 spans ≈ 80 s of ClickHouse outage at the 50 rps of G-TRACE-0 before the first drop; ~2 KB each, ~8 MB
# of memory at worst. Batches of 512 or one per second: few, large inserts, the way ClickHouse likes them.
QUEUE_CAPACITY = 4096
BATCH_SIZE = 512
FLUSH_INTERVAL_S = 1.0
# Short on purpose: a hung ClickHouse holds the export worker for at most this long per batch. The request
# never waits for it at all (R1); these only bound how fast the queue notices.
CONNECT_TIMEOUT_S = 2
SEND_RECEIVE_TIMEOUT_S = 5

app = typer.Typer(no_args_is_help=True, add_completion=False)

ClickHouseUrl = Annotated[
    str | None,
    typer.Option(
        "--clickhouse",
        envvar="EVALGATE_CLICKHOUSE_URL",
        help="ClickHouse DSN for traces, e.g. http://default:@localhost:8123/default. Unset: no traces.",
    ),
]


def connector(dsn: str) -> Callable[[], StoreClient]:
    def connect() -> StoreClient:
        client: StoreClient = clickhouse_connect.get_client(
            dsn=dsn, connect_timeout=CONNECT_TIMEOUT_S, send_receive_timeout=SEND_RECEIVE_TIMEOUT_S
        )
        return client

    return connect


def trace_sink(dsn: str) -> Callable[[LlmCall], None]:
    """proxy → LlmCall → span → bounded queue → ClickHouse. Connects nothing yet: the exporter is lazy."""
    return build_pipeline(
        ClickHouseSpanExporter(connector(dsn)),
        capacity=QUEUE_CAPACITY,
        batch_size=BATCH_SIZE,
        flush_interval_s=FLUSH_INTERVAL_S,
        service_name="evalgate",
        meter=metrics.get_meter("evalgate", version("evalgate")),
    ).sink


@app.callback()
def main() -> None:
    """Evalgate: quality gate for LLM applications."""


@app.command()
def serve(  # noqa: PLR0913, PLR0917 - in typer each flag IS a parameter
    host: Annotated[str, typer.Option(help="Interface to bind.")] = "127.0.0.1",
    port: Annotated[int, typer.Option(help="Port to listen on.")] = 8080,
    upstream: Annotated[
        str, typer.Option(envvar="EVALGATE_UPSTREAM_BASE_URL", help="OpenAI-compatible upstream base URL.")
    ] = DEFAULT_UPSTREAM,
    normalize: Annotated[
        bool,
        typer.Option(envvar="EVALGATE_NORMALIZE", help="Add schema-required nullable fields (ADR-007)."),
    ] = True,
    provider: Annotated[
        str,
        typer.Option(envvar="EVALGATE_PROVIDER", help="Provider name the traces report (ollama, openai…)."),
    ] = DEFAULT_PROVIDER,
    clickhouse: ClickHouseUrl = None,
    pricing_dir: Annotated[
        Path,
        typer.Option(envvar="EVALGATE_PRICING_DIR", help="Published price tables and their TABLES.lock."),
    ] = Path("pricing"),
) -> None:
    """Run the proxy. Point a client's OPENAI_BASE_URL at http://HOST:PORT/v1."""
    settings = ProxySettings(
        upstream_base_url=upstream,
        normalize=normalize,
        provider=provider,
        # Fails here, at start-up and loudly, if a published table was edited, deleted or never sealed (R4):
        # better no proxy than a proxy pricing with a table nobody can vouch for.
        price_tables=load_tables(pricing_dir, pricing_dir / "TABLES.lock"),
        on_call=trace_sink(clickhouse) if clickhouse else None,
    )
    uvicorn.run(create_app(settings), host=host, port=port, log_level="warning")


@app.command()
def migrate(clickhouse: ClickHouseUrl = None) -> None:
    """Apply the pending ClickHouse migrations (create_schema: false; the schema is ours and versioned)."""
    if not clickhouse:
        raise typer.BadParameter("hace falta --clickhouse o EVALGATE_CLICKHOUSE_URL")
    applied = apply(connector(clickhouse)())
    typer.echo(f"migraciones aplicadas: {[m.version for m in applied] or 'ninguna pendiente'}")


eval_app = typer.Typer(no_args_is_help=True, help="Evaluation suites (level 4).")
app.add_typer(eval_app, name="eval")


@eval_app.command("pricing-repro")
def eval_pricing_repro(
    suite_dir: Annotated[Path, typer.Option(help="Corpus directory.")] = Path("evals/suites/pricing-repro"),
    out: Annotated[Path, typer.Option(help="Report to write.")] = Path("evals/reports/pricing-repro.json"),
) -> None:
    """G-PRICE-REPRO: recompute the fixed corpus of cost reports with the table in force at each date."""
    worst = pricing_repro.run(suite_dir, out)
    typer.echo(f"{pricing_repro.GOAL} diff_max_eur={format(worst.normalize(), 'f')} informe={out}")
    if worst != 0:
        raise typer.Exit(code=1)


@eval_app.command("compare")
def eval_compare(
    base: Annotated[Path, typer.Argument(help="Eval report of the baseline.")],
    head: Annotated[Path, typer.Argument(help="Eval report of the change.")],
    gate: Annotated[Path, typer.Option(help="Metric rules of the suite (gate.yaml).")],
    out: Annotated[Path, typer.Option(help="Comparison report to write.")],
    goals: Annotated[Path, typer.Option(help="Where `comparacion` lives.")] = Path("docs/GOALS.yaml"),
) -> None:
    """The gate: exit 0 if HEAD may merge, 1 if it is blocked, 2 if the reports cannot be compared."""
    try:
        comparison = compare_cli.run(base, head, gate, goals, out)
    except ValueError as refused:
        typer.echo(f"evalgate eval compare: {refused}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(compare_cli.table(comparison))
    if comparison.outcome == BLOCK:
        raise typer.Exit(code=1)
