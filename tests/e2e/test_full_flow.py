"""Level 5, the whole path: bring everything up, generate traffic, see the traces arrive,
run the evals, provoke a regression and watch the gate block it.

Everything is the real thing through its command line: `evalgate serve` in front of the example app, a real
ClickHouse in a container, `evalgate eval run` and `evalgate eval compare`. Only the model is a stub
(tests/e2e/stub_upstream.py), so the test says the same every time; the evals run from the outputs and
verdicts recorded in the repository. Needs Docker.
"""

import os
import shutil
import subprocess
import sys
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import clickhouse_connect
import pytest
from testcontainers.community.clickhouse import ClickHouseContainer

from evalgate.telemetry.migrations import apply
from evalgate.telemetry.rows import TRACES_TABLE

from .test_adoption import QUESTIONS, RAG_APP, ROOT, free_port, wait_for_port, wait_until_up

# The image of the integration level, pinned by digest (R18). ClickHouse 26.4.
CLICKHOUSE_IMAGE = (
    "clickhouse/clickhouse-server@sha256:c7796a1335d14385c052f10061cf719f4a368a908432ec25980860b1333e9ccd"
)
SUITE = "rag-app-v2"
EVALGATE = shutil.which("evalgate", path=str(Path(sys.executable).parent))


def evalgate(*args: str, cwd: Path = ROOT) -> subprocess.CompletedProcess[str]:
    assert EVALGATE is not None, "the `evalgate` console script is not installed in this venv"
    return subprocess.run(
        [EVALGATE, *args], cwd=cwd, capture_output=True, text=True, check=False, timeout=300
    )


@pytest.fixture(scope="module")
def store() -> Iterator[str]:
    with ClickHouseContainer(CLICKHOUSE_IMAGE) as container:
        host, port = container.get_container_host_ip(), container.get_exposed_port(8123)
        dsn = f"http://{container.username}:{container.password}@{host}:{port}/default"
        client: Any = clickhouse_connect.get_client(dsn=dsn)
        try:
            apply(client)
        finally:
            client.close()
        yield dsn


@pytest.fixture(scope="module")
def proxy(store: str) -> Iterator[str]:
    """A stub model, and `evalgate serve` in front of it writing its traces to the store."""
    assert EVALGATE is not None
    upstream_port, port = free_port(), free_port()
    stub = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "stub_upstream.py"), "--port", str(upstream_port)]
    )
    server = None
    try:
        wait_for_port(upstream_port)
        server = subprocess.Popen(
            [
                EVALGATE,
                "serve",
                "--port",
                str(port),
                "--upstream",
                f"http://127.0.0.1:{upstream_port}/v1",
                "--clickhouse",
                store,
            ]
        )
        wait_until_up(f"http://127.0.0.1:{port}/healthz")
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        for process in (server, stub):
            if process is not None:
                process.terminate()
                process.wait(timeout=10)


def _traces(dsn: str) -> list[tuple[Any, ...]]:
    client: Any = clickhouse_connect.get_client(dsn=dsn)
    try:
        rows: list[tuple[Any, ...]] = client.query(f"SELECT SpanAttributes FROM {TRACES_TABLE}").result_rows  # noqa: S608 - a constant of ours
        return rows
    finally:
        client.close()


def test_traffic_through_the_proxy_arrives_as_one_trace_per_call_with_its_tokens(
    store: str, proxy: str
) -> None:
    done = subprocess.run(
        [sys.executable, "rag_app.py", "--limit", str(QUESTIONS)],
        cwd=RAG_APP,
        env={**os.environ, "OPENAI_BASE_URL": proxy, "RAG_MODEL": "qwen3.5:4b-mlx"},
        capture_output=True,
        text=True,
        timeout=300,
        check=True,
    )
    assert len(done.stdout.splitlines()) == QUESTIONS

    deadline = time.monotonic() + 20  # the export is batched and never awaited by the request (R1)
    rows = _traces(store)
    while len(rows) < QUESTIONS and time.monotonic() < deadline:
        time.sleep(0.25)
        rows = _traces(store)

    assert len(rows) == QUESTIONS, "one trace per call: none lost, none invented"
    for (attributes,) in rows:
        tokens = {key: value for key, value in attributes.items() if key.endswith("_tokens")}
        assert tokens, f"a trace without its token counts: {sorted(attributes)}"
        assert all(int(value) > 0 for value in tokens.values()), tokens


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    """What an evaluation reads, copied: the suite with its recorded outputs and verdicts, and the goals."""
    for relative in ("prompts", f"evals/golden/{SUITE}", f"evals/suites/{SUITE}"):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "GOALS.yaml", tmp_path / "docs" / "GOALS.yaml")
    return tmp_path


def _compare(workspace: Path, head: str) -> subprocess.CompletedProcess[str]:
    return evalgate(
        "eval",
        "compare",
        f"base/{SUITE}.json",
        f"{head}/{SUITE}.json",
        "--gate",
        f"evals/suites/{SUITE}/gate.yaml",
        "--out",
        f"{head}-comparison.json",
        cwd=workspace,
    )


def test_the_gate_lets_the_same_system_through_and_blocks_a_regression(workspace: Path) -> None:
    assert evalgate("eval", "run", "--suite", SUITE, "--out-dir", "base", cwd=workspace).returncode == 0

    # the same system, evaluated again: nothing changed, nothing to block
    assert evalgate("eval", "run", "--suite", SUITE, "--out-dir", "same", cwd=workspace).returncode == 0
    same = _compare(workspace, "same")
    assert same.returncode == 0, same.stdout + same.stderr
    assert "decisión: PASS" in same.stdout

    # the regression: the system now answers with half of the retrieved context (recorded, with verdicts)
    sut = workspace / "evals/suites" / SUITE / "sut"
    shutil.copy(sut / "contexto-50.jsonl", sut / "base.jsonl")
    assert evalgate("eval", "run", "--suite", SUITE, "--out-dir", "worse", cwd=workspace).returncode == 0
    worse = _compare(workspace, "worse")

    assert worse.returncode == 1, worse.stdout + worse.stderr
    assert "decisión: BLOCK" in worse.stdout
    blocked = [line.split()[0] for line in worse.stdout.splitlines() if "BLOQUEA" in line]
    assert blocked == ["answer_correct", "abstencion_incorrecta"]
