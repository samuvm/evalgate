"""`make bench PROFILE=proxy|stream`: G-LAT-PROXY and G-LAT-TTFT, exactly as docs/bench/protocol.md says.

Three processes, so no one steals the other's GIL: the loopback stub (scripts/bench_stub.py), the REAL proxy
started with `evalgate serve --clickhouse` (tracing ON, into a real ClickHouse: measuring without the trace
pipeline would publish an overhead nobody runs), and this client. Arms interleaved (direct, proxy, direct…),
concurrency 1, one `httpx` client with `max_connections=100` reused by both arms. 50 warm-up + 500 measured
per arm. The published number is the DIFFERENCE OF PERCENTILES; the paired differences are kept as diagnosis.

`--smoke` checks that the machinery works with a handful of requests and writes nowhere near evals/reports/:
a smoke number is not a measurement and must never be mistaken for one.

Usage: python scripts/bench.py --profile proxy|stream [--smoke --out PATH]
"""

import argparse
import hashlib
import json
import platform
import socket
import subprocess
import sys
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from testcontainers.community.clickhouse import ClickHouseContainer

ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "docs" / "bench" / "protocol.md"
# Same digest as tests/integration/conftest.py (R18).
CLICKHOUSE_IMAGE = (
    "clickhouse/clickhouse-server@sha256:c7796a1335d14385c052f10061cf719f4a368a908432ec25980860b1333e9ccd"
)
N_WARMUP, N_MEASURED = 50, 500
PROMPT = " ".join(f"w{i % 97}" for i in range(512))  # 512 whitespace tokens, the same in every request


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def wait_healthy(url: str, seconds: float = 30) -> None:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        try:
            if httpx.get(url, timeout=1).status_code == 200:
                return
        except httpx.HTTPError:
            pass
        time.sleep(0.2)
    raise SystemExit(f"bench: {url} no respondió en {seconds} s")


@contextmanager
def process(args: list[str], health: str) -> Iterator[None]:
    child = subprocess.Popen(args, cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        wait_healthy(health)
        yield
    finally:
        child.terminate()
        child.wait(timeout=10)


def body(stream: bool) -> bytes:
    payload = {"model": "bench-stub", "messages": [{"role": "user", "content": PROMPT}], "stream": stream}
    return json.dumps(payload).encode()


def total_ms(client: httpx.Client, url: str) -> float:
    started = time.perf_counter_ns()
    response = client.post(url, content=body(stream=False), headers={"content-type": "application/json"})
    response.read()
    elapsed = (time.perf_counter_ns() - started) / 1e6
    if response.status_code != 200:
        raise SystemExit(f"bench: {url} → {response.status_code}")
    return elapsed


def ttft_ms(client: httpx.Client, url: str) -> float:
    """Send → first byte of the first chunk WITH CONTENT (protocol §6). The rest is drained, not timed."""
    started = time.perf_counter_ns()
    first: float | None = None
    with client.stream(
        "POST", url, content=body(stream=True), headers={"content-type": "application/json"}
    ) as r:
        for piece in r.iter_raw():
            if first is None and b'"content":"' in piece and b'"content":""' not in piece:
                first = (time.perf_counter_ns() - started) / 1e6
    if first is None:
        raise SystemExit(f"bench: {url} no emitió ningún chunk con contenido")
    return first


def percentile(values: list[float], q: float) -> float:
    ordered = sorted(
        values
    )  # nearest rank: no interpolation, no outlier removal (protocol, "Qué no se hace")
    return ordered[max(0, min(len(ordered) - 1, int(q / 100 * len(ordered) + 0.5) - 1))]


def shell(command: list[str]) -> str:
    try:
        return subprocess.run(command, capture_output=True, text=True, timeout=10, check=False).stdout.strip()
    except (OSError, subprocess.TimeoutExpired) as exc:
        return f"<no disponible: {type(exc).__name__}>"


def hardware() -> dict[str, Any]:
    """Read from THIS machine (protocol, "Informe"), never copied from STACK.md."""
    return {
        "model": shell(["sysctl", "-n", "hw.model"]),
        "chip": shell(["sysctl", "-n", "machdep.cpu.brand_string"]),
        "memory_bytes": int(shell(["sysctl", "-n", "hw.memsize"]) or 0),
        "cores": int(shell(["sysctl", "-n", "hw.ncpu"]) or 0),
        "macos": shell(["sw_vers", "-productVersion"]),
        "machine": platform.machine(),
    }


def run(profile: str, n_warmup: int, n_measured: int) -> dict[str, Any]:
    measure: Callable[[httpx.Client, str], float] = total_ms if profile == "proxy" else ttft_ms
    stub_port, proxy_port = free_port(), free_port()
    direct = f"http://127.0.0.1:{stub_port}/v1/chat/completions"
    via_proxy = f"http://127.0.0.1:{proxy_port}/v1/chat/completions"
    with ClickHouseContainer(CLICKHOUSE_IMAGE) as clickhouse:
        dsn = (
            f"http://{clickhouse.username}:{clickhouse.password}@{clickhouse.get_container_host_ip()}:"
            f"{clickhouse.get_exposed_port(8123)}/default"
        )
        subprocess.run(
            ["evalgate", "migrate", "--clickhouse", dsn], cwd=ROOT, check=True, capture_output=True
        )
        concurrent = {
            "docker_ps": shell(["docker", "ps", "--format", "{{.Names}} {{.Image}}"]),
            "ollama_ps": shell(["ollama", "ps"]),
        }
        stub = [sys.executable, "scripts/bench_stub.py", "--port", str(stub_port)]
        proxy = [
            "evalgate",
            "serve",
            "--port",
            str(proxy_port),
            "--upstream",
            f"http://127.0.0.1:{stub_port}/v1",
            "--clickhouse",
            dsn,
        ]
        with (
            process(stub, f"http://127.0.0.1:{stub_port}/healthz"),
            process(proxy, f"http://127.0.0.1:{proxy_port}/healthz"),
            httpx.Client(limits=httpx.Limits(max_connections=100), timeout=30) as client,
        ):
            arms: dict[str, list[float]] = {"direct": [], "proxy": []}
            for i in range(n_warmup + n_measured):
                pair = (measure(client, direct), measure(client, via_proxy))
                if i >= n_warmup:
                    arms["direct"].append(pair[0])
                    arms["proxy"].append(pair[1])
    key = "overhead_ms" if profile == "proxy" else "ttft_overhead_ms"
    paired = [p - d for d, p in zip(arms["direct"], arms["proxy"], strict=True)]
    ours = [line for line in concurrent["docker_ps"].splitlines() if "clickhouse-server" not in line]
    return {
        "profile": profile,
        key: {
            q: round(percentile(arms["proxy"], v) - percentile(arms["direct"], v), 3)
            for q, v in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "direct_ms": {
            q: round(percentile(arms["direct"], v), 3) for q, v in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "proxy_ms": {
            q: round(percentile(arms["proxy"], v), 3) for q, v in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "paired_diff_ms": {
            q: round(percentile(paired, v), 3) for q, v in (("p50", 50), ("p95", 95), ("p99", 99))
        },
        "n": n_measured,
        "n_warmup": n_warmup,
        "tracing": "clickhouse (evalgate serve --clickhouse), mismo digest que el nivel 2",
        "hardware": hardware(),
        "python": platform.python_version(),
        "concurrent_processes": concurrent,
        # Exclusivity (Q-005 (a)): our own ClickHouse is part of the system under test; anything else is not.
        "exclusive_window": not ours and len(concurrent["ollama_ps"].splitlines()) <= 1,
        "protocol_sha256": hashlib.sha256(PROTOCOL.read_bytes()).hexdigest(),
        "measured_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--profile", choices=["proxy", "stream"], required=True)
    parser.add_argument(
        "--smoke", action="store_true", help="5 + 2 peticiones; nunca escribe en evals/reports/"
    )
    parser.add_argument("--out", type=Path, help="solo con --smoke")
    args = parser.parse_args()
    if args.smoke:
        if args.out is None or ROOT / "evals" in args.out.resolve().parents:
            raise SystemExit("bench: --smoke exige --out fuera de evals/: un humo no es una medida")
        report, out = run(args.profile, 2, 5), args.out
    else:
        report = run(args.profile, N_WARMUP, N_MEASURED)
        out = ROOT / "evals" / "reports" / f"bench-{args.profile}-{datetime.now(UTC).date().isoformat()}.json"
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    key = "overhead_ms" if args.profile == "proxy" else "ttft_overhead_ms"
    print(f"bench {args.profile}: {key}={report[key]} n={report['n']} exclusiva={report['exclusive_window']}")
    print(f"informe: {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
