"""`evalgate` CLI. Wiring only: excluded from unit tests (RULES §2), covered by e2e and integration.

This is where the trace pipeline is assembled, and the only place that sees both ends of it: the proxy gets a
plain `on_call` sink and never an exporter (R1, `scripts/rules/no_blocking_export.py`).
"""

import json
import tempfile
from collections.abc import Callable
from importlib.metadata import version
from pathlib import Path
from typing import Annotated, Any

import clickhouse_connect
import typer
import uvicorn
import yaml
from opentelemetry import metrics

from evalgate.cli import compare as compare_cli
from evalgate.cli import eval_run, matrix, meta, pricing_repro, self_gate
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
    except (ValueError, LookupError, OSError) as refused:  # a missing file is "cannot compare", not "blocked"
        typer.echo(f"evalgate eval compare: {refused}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(compare_cli.table(comparison))
    if comparison.outcome == BLOCK:
        raise typer.Exit(code=1)


@eval_app.command("self-gate")
def eval_self_gate(
    suite: Annotated[
        list[str] | None, typer.Option(help="Suites to hold behind the gate. Default: all with a baseline.")
    ] = None,
) -> None:
    """R16: this repository behind its own gate. The published report of each suite is the baseline; what
    today's code gives from the recorded outputs is HEAD. Exit 0, 1 if blocked, 2 if it cannot be compared."""
    blocked = False
    for name in suite or self_gate.SUITES:
        try:
            comparison = self_gate.check(Path(), name)
        except (ValueError, LookupError, OSError) as refused:
            typer.echo(f"evalgate eval self-gate: {name}: {refused}", err=True)
            raise typer.Exit(code=2) from None
        typer.echo(f"== {name}\n{compare_cli.table(comparison)}")
        blocked = blocked or comparison.outcome == BLOCK
    if blocked:
        raise typer.Exit(code=1)


@eval_app.command("run")
def eval_run_command(  # noqa: PLR0913, PLR0917 - in typer each flag IS a parameter
    suite: Annotated[str, typer.Option(help="Suite name, as in evals/suites/.")] = "rag-app",
    refresh: Annotated[
        bool, typer.Option(help="Call the models for what is not recorded. Never in the gate.")
    ] = False,
    base_url: Annotated[
        str,
        typer.Option(
            envvar="EVALGATE_EVAL_BASE_URL", help="OpenAI-compatible endpoint, only with --refresh."
        ),
    ] = DEFAULT_UPSTREAM,
    out_dir: Annotated[Path, typer.Option(help="Where the report goes.")] = Path("evals/reports"),
    variant: Annotated[
        str, typer.Option(help="Variant of the system under test, as the suite declares it.")
    ] = "base",
    rejudge: Annotated[
        bool,
        typer.Option(
            help="Keep the recorded outputs of the system; call the judge for what is not recorded."
        ),
    ] = False,
) -> None:
    """Run an eval suite from the recorded cache (default) or against the models (--refresh)."""
    try:
        report, stats = eval_run.run(
            Path("evals/suites") / suite,
            Path(),
            out_dir,
            refresh=refresh,
            base_url=base_url,
            variant=variant,
            rejudge=rejudge,
        )
    except (ValueError, LookupError, OSError) as refused:
        typer.echo(f"evalgate eval run: {refused}", err=True)
        raise typer.Exit(code=2) from None
    for metric in report["metrics"]:
        typer.echo(f"{metric['id']:24} {metric['value']:.4f}  n={metric['n']}")
    typer.echo(
        f"caché de jueces: {stats.hits} aciertos, {stats.misses} fallos · "
        f"coste marginal {stats.marginal_cost_ratio:.4f} · {report['run_id']} en {out_dir}"
    )


cache_app = typer.Typer(no_args_is_help=True, help="The recorded cache of model calls.")
app.add_typer(cache_app, name="cache")


@cache_app.command("stats")
def cache_stats_command(
    suite: Annotated[str, typer.Option(help="Suite name.")] = "rag-app",
    out: Annotated[Path, typer.Option(help="Artefact of G-CACHE-HIT.")] = Path(
        "evals/reports/cache-stats.json"
    ),
    fmt: Annotated[str, typer.Option("--format", help="json or text.")] = "text",
) -> None:
    """G-CACHE-HIT: what the last two runs of a suite cost. Needs two runs (`make eval && make eval`)."""
    try:
        document = eval_run.cache_stats(suite, Path(), out)
    except ValueError as refused:
        typer.echo(f"evalgate cache stats: {refused}", err=True)
        raise typer.Exit(code=2) from None
    if fmt == "json":
        typer.echo(json.dumps(document, ensure_ascii=False))
    else:
        second = document["second_run"]
        typer.echo(
            f"G-CACHE-HIT marginal_cost_ratio={second['marginal_cost_ratio']:g} "
            f"hit_rate={second['hit_rate']:g} hits={second['hits']} misses={second['misses']}"
        )


meta_app = typer.Typer(no_args_is_help=True, help="Meta-evaluation: the evaluator, evaluated (level 4).")
app.add_typer(meta_app, name="meta")


@meta_app.command("kappa")
def meta_kappa_command(  # noqa: PLR0913, PLR0917 - in typer each flag IS a parameter
    labels: Annotated[Path, typer.Option(help="Directory of the human labels, with its kappa.yaml.")] = Path(
        "evals/golden/rag-app-v2/labels"
    ),
    out: Annotated[Path, typer.Option(help="Meta-eval document to update.")] = Path(
        "evals/reports/meta-eval.json"
    ),
    goals: Annotated[Path, typer.Option(help="Where `comparacion` lives.")] = Path("docs/GOALS.yaml"),
    refresh: Annotated[
        bool, typer.Option(help="Call the judge for verdicts that are not recorded. Never in the gate.")
    ] = False,
    base_url: Annotated[
        str, typer.Option(envvar="EVALGATE_EVAL_BASE_URL", help="Endpoint of the judge, only with --refresh.")
    ] = DEFAULT_UPSTREAM,
    fmt: Annotated[str, typer.Option("--format", help="json or text.")] = "text",
) -> None:
    """G-JUDGE-KAPPA: Cohen's kappa of the suite's judge against the human labels, with its interval."""
    try:
        document = meta.run(labels, Path(), goals, out, refresh=refresh, base_url=base_url)
    except (ValueError, LookupError, OSError) as refused:
        typer.echo(f"evalgate meta kappa: {refused}", err=True)
        raise typer.Exit(code=2) from None
    kappa = document["cohens_kappa"]
    if fmt == "json":
        typer.echo(json.dumps(kappa, ensure_ascii=False))
    else:
        low, high = kappa["ci95_bootstrap"]
        typer.echo(
            f"G-JUDGE-KAPPA kappa={kappa['point']:.4f} ic95=[{low:.4f}, {high:.4f}] n={kappa['n']} "
            f"acuerdo={kappa['raw_agreement']:.4f} tandas={kappa['batches']} "
            f"juez={kappa['judge']['prompt_id']} v{kappa['judge']['prompt_version']}"
        )


@meta_app.command("run-matrix")
def meta_run_matrix_command(
    plan: Annotated[Path, typer.Option(help="What to execute: the suite's matrix.yaml.")] = Path(
        "evals/suites/rag-app-v2/matrix.yaml"
    ),
    raw: Annotated[Path, typer.Option(help="One file per run: answers and verdicts.")] = Path(
        "evals/reports/fp-matrix"
    ),
    out: Annotated[Path, typer.Option(help="The matrix: (run_id, case_id, metrica, valor).")] = Path(
        "evals/reports/fp-matrix.parquet"
    ),
    base_url: Annotated[
        str, typer.Option(envvar="EVALGATE_EVAL_BASE_URL", help="OpenAI-compatible endpoint of the models.")
    ] = DEFAULT_UPSTREAM,
    build_only: Annotated[
        bool, typer.Option(help="Call no model: rebuild the matrix from the runs already recorded.")
    ] = False,
) -> None:
    """RULES §5: run the calibration subsuite many times, with noise, and persist the matrix. Hours of
    models; resumable (a recorded run is never executed again). Never in the gate."""
    try:
        if not build_only:
            executed = matrix.record(plan, Path(), raw, base_url, typer.echo)
            typer.echo(f"{executed} ejecuciones grabadas ahora en {raw}")
        metadata = matrix.build(plan, Path(), raw, out)
    except (ValueError, LookupError, OSError, RuntimeError) as refused:
        typer.echo(f"evalgate meta run-matrix: {refused}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(f"{out}: {len(metadata['runs'])} ejecuciones de {metadata['n_cases']} casos")


_MATRIX = Annotated[Path, typer.Option("--matrix", help="The matrix written by `meta run-matrix`.")]
_META_OUT = Annotated[Path, typer.Option(help="Meta-eval document to update.")]
_GOALS = Annotated[Path, typer.Option(help="Where `comparacion` lives.")]
_FORMAT = Annotated[str, typer.Option("--format", help="json or text.")]
_DEFAULT_MATRIX = Path("evals/reports/fp-matrix.parquet")
_DEFAULT_META = Path("evals/reports/meta-eval.json")
_DEFAULT_GOALS = Path("docs/GOALS.yaml")


def _from_matrix(
    name: str, measure: Callable[[Path, Path, Path, Path], dict[str, object]], paths: tuple[Path, Path, Path]
) -> dict[str, object]:
    matrix_path, goals, out = paths
    try:
        return measure(matrix_path, Path(), goals, out)
    except (ValueError, LookupError, OSError) as refused:
        typer.echo(f"evalgate meta {name}: {refused}", err=True)
        raise typer.Exit(code=2) from None


@meta_app.command("fp")
def meta_fp_command(
    matrix_path: _MATRIX = _DEFAULT_MATRIX,
    out: _META_OUT = _DEFAULT_META,
    goals: _GOALS = _DEFAULT_GOALS,
    fmt: _FORMAT = "text",
) -> None:
    """G-GATE-FP: how often the gate blocks the system against itself. Offline, from the matrix."""
    document = _from_matrix("fp", meta.fp, (matrix_path, goals, out))
    block: dict[str, Any] = document["fp_rate_baseline_fixed"]  # type: ignore[assignment]
    if fmt == "json":
        typer.echo(json.dumps(block, ensure_ascii=False))
    else:
        low, high = block["wilson_95"]
        typer.echo(
            f"G-GATE-FP fp={block['point']:.4f} wilson95=[{low:.4f}, {high:.4f}] "
            f"bloqueos={block['blocked']}/{block['n']} por_métrica={block['blocked_by_metric']} "
            f"bloqueantes={block['blocking_metrics']}"
        )


@meta_app.command("mde")
def meta_mde_command(
    matrix_path: _MATRIX = _DEFAULT_MATRIX,
    out: _META_OUT = _DEFAULT_META,
    goals: _GOALS = _DEFAULT_GOALS,
    fmt: _FORMAT = "text",
) -> None:
    """G-GATE-MDE: the drop that noise alone rarely reaches, in points. Offline, from the matrix."""
    document = _from_matrix("mde", meta.mde, (matrix_path, goals, out))
    block: dict[str, Any] = document["mde_pp"]  # type: ignore[assignment]
    if fmt == "json":
        typer.echo(json.dumps(block, ensure_ascii=False))
    else:
        each = " ".join(f"{metric}={values['point']:.2f}" for metric, values in block["per_metric"].items())
        typer.echo(
            f"G-GATE-MDE mde_pp={block['point']:.2f} ({block['limiting_metric']}) · {each} · "
            f"{block['n_pairs']} pares de {block['n_runs']} ejecuciones"
        )


@meta_app.command("sensitivity")
def meta_sensitivity_command(
    matrix_path: _MATRIX = _DEFAULT_MATRIX,
    out: _META_OUT = _DEFAULT_META,
    goals: _GOALS = _DEFAULT_GOALS,
    fmt: _FORMAT = "text",
) -> None:
    """G-GATE-POWER: how often the gate blocks each canonical degradation. Offline, from the matrix."""
    document = _from_matrix("sensitivity", meta.sensitivity, (matrix_path, goals, out))
    block: dict[str, Any] = document["power"]  # type: ignore[assignment]
    if fmt == "json":
        typer.echo(json.dumps(block, ensure_ascii=False))
        return
    typer.echo(
        f"G-GATE-POWER min={block['min_over_degradations']} (exigida a tamaño >= "
        f"{block['required_size_pp']:.2f} pp) · mínimo sobre todas={block['min_over_all']:.2f}"
    )
    for name, each in block["per_degradation"].items():
        typer.echo(
            f"  {name:20} potencia={each['power']:.2f} ({each['blocked']}/{each['n']}) "
            f"tamaño={each['size_pp']:.1f} pp en {each['size_metric']}"
            f"{'' if each['big_enough'] else '  [por debajo del tamaño exigido]'}"
        )


@meta_app.command("report")
def meta_report_command(
    check: Annotated[
        bool, typer.Option(help="Measure everything again from its sources; fail if the document differs.")
    ] = False,
    document: _META_OUT = _DEFAULT_META,
    matrix_path: _MATRIX = _DEFAULT_MATRIX,
    labels: Annotated[Path, typer.Option(help="Directory of the human labels.")] = Path(
        "evals/golden/rag-app-v2/labels"
    ),
    goals: _GOALS = _DEFAULT_GOALS,
) -> None:
    """The four numbers of the meta-evaluation against their thresholds. With --check, also proves that the
    published document is what the labels and the matrix give today. Exit 1 if it is not."""
    try:
        published = json.loads(document.read_text("utf-8"))
        table = meta.report_table(published, yaml.safe_load(goals.read_text("utf-8")))
        if check:
            with tempfile.TemporaryDirectory() as scratch:
                again = meta.recomputed(labels, matrix_path, Path(), goals, Path(scratch) / "meta-eval.json")
            if again != published:
                differing = sorted(
                    key for key in again.keys() | published.keys() if again.get(key) != published.get(key)
                )
                typer.echo(
                    f"evalgate meta report: el documento no se reproduce en: {', '.join(differing)}", err=True
                )
                raise typer.Exit(code=1)
    except (ValueError, LookupError, OSError) as refused:
        typer.echo(f"evalgate meta report: {refused}", err=True)
        raise typer.Exit(code=2) from None
    typer.echo(table)
    if check:
        typer.echo("\nreproducido desde las etiquetas y la matriz: sin diferencias")
