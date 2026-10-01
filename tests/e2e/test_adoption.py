"""G-ADOPTION (criterio de aceptación nº 1): an existing app is instrumented by changing one environment
variable, without touching code. Measured as the number of differing output lines of examples/rag-app
run straight against the upstream and through `evalgate serve`. Must be 0.

Upstream: a deterministic stub by default (tests/e2e/stub_upstream.py). Set EVALGATE_E2E_UPSTREAM to a real
OpenAI-compatible base URL (e.g. http://localhost:11434/v1) to run the same measurement against Ollama.
"""

import difflib
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
RAG_APP = ROOT / "examples" / "rag-app"
QUESTIONS = 8


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port: int = s.getsockname()[1]
        return port


def wait_until_up(url: str, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1):
                return
        except OSError:
            time.sleep(0.1)
    raise TimeoutError(f"{url} did not come up in {timeout_s} s")


def wait_for_port(port: int, timeout_s: float = 20.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        with socket.socket() as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"port {port} did not open in {timeout_s} s")


@pytest.fixture(scope="module")
def upstream() -> Iterator[str]:
    real = os.environ.get("EVALGATE_E2E_UPSTREAM")
    if real:
        yield real
        return
    port = free_port()
    stub = subprocess.Popen(
        [sys.executable, str(Path(__file__).parent / "stub_upstream.py"), "--port", str(port)]
    )
    try:
        wait_for_port(port)
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        stub.terminate()
        stub.wait(timeout=10)


@pytest.fixture(scope="module")
def proxy(upstream: str) -> Iterator[str]:
    port = free_port()
    evalgate = shutil.which("evalgate", path=str(Path(sys.executable).parent))
    assert evalgate is not None, "the `evalgate` console script is not installed in this venv"
    server = subprocess.Popen([evalgate, "serve", "--port", str(port), "--upstream", upstream])
    try:
        wait_until_up(f"http://127.0.0.1:{port}/healthz")
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        server.terminate()
        server.wait(timeout=10)


def run_app(base_url: str) -> list[str]:
    env = {
        **os.environ,
        "OPENAI_BASE_URL": base_url,
        "RAG_MODEL": os.environ.get("RAG_MODEL", "qwen3.5:4b-mlx"),
    }
    result = subprocess.run(
        [sys.executable, "rag_app.py", "--limit", str(QUESTIONS)],
        cwd=RAG_APP,
        env=env,
        capture_output=True,
        text=True,
        timeout=900,
        check=True,
    )
    return result.stdout.splitlines()


def test_adoption_changes_zero_output_lines(upstream: str, proxy: str) -> None:
    direct = run_app(upstream)
    through_proxy = run_app(proxy)
    changed = [
        line
        for line in difflib.unified_diff(direct, through_proxy, lineterm="", n=0)
        if line[:1] in "+-" and not line.startswith(("+++", "---"))
    ]

    print(f"G-ADOPTION lineas_de_diff={len(changed)} n_lineas={len(direct)}")
    assert len(direct) == QUESTIONS, "the app produced no output: a vacuous diff proves nothing"
    assert changed == []
