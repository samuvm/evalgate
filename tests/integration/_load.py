"""Paced load through the REAL proxy app (ASGI, in process) against an instant upstream stub.

The upstream is a stub on purpose: what G-TRACE-0 and G-TRACE-DEGRADE measure is the trace pipeline, and a
real model would add seconds of variance per request that have nothing to do with it (RULES §3.5).
Concurrency 1 and a fixed schedule (request i leaves at t0 + i/rps): a sustained rate, not a burst.
"""

import asyncio
import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from evalgate.proxy.app import ProxySettings, create_app
from evalgate.telemetry.model import LlmCall

UPSTREAM = "http://upstream.test/v1"
ASKED = b'{"model":"qwen3.5:4b-mlx","messages":[{"role":"user","content":"precio?"}],"max_tokens":16}'
ANSWER = (
    b'{"id":"c1","object":"chat.completion","created":1,"model":"qwen3.5:4b-mlx","choices":[{"index":0,'
    b'"message":{"role":"assistant","content":"42"},"finish_reason":"stop"}],'
    b'"usage":{"prompt_tokens":15,"completion_tokens":1,"total_tokens":16}}'
)


def _answer(request: httpx.Request) -> httpx.Response:  # noqa: ARG001 · MockTransport's signature
    return httpx.Response(200, content=ANSWER, headers={"content-type": "application/json"})


@dataclass
class Served:
    latencies_ms: list[float] = field(default_factory=list)
    statuses: list[int] = field(default_factory=list)

    @property
    def ok(self) -> int:
        return sum(status == 200 for status in self.statuses)


def p95(values: list[float]) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(0.95 * len(ordered) + 0.5) - 1)]


async def serve(
    sink: Callable[[LlmCall], None],
    rps: float,
    requests: int,
    *,
    at: dict[int, Callable[[], Awaitable[None]]] | None = None,
) -> Served:
    """Send `requests` chat calls at `rps`. `at[i]` is started (not awaited) just before request i."""
    settings = ProxySettings(upstream_base_url=UPSTREAM, on_call=sink)
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(_answer))
    app = create_app(settings, client=upstream)
    served, pending = Served(), []
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://proxy") as client:
        start = time.perf_counter()
        for i in range(requests):
            if at and i in at:
                pending.append(asyncio.create_task(at[i]()))
            await asyncio.sleep(max(0.0, start + i / rps - time.perf_counter()))
            sent = time.perf_counter()
            response = await client.post("/v1/chat/completions", content=ASKED)
            served.latencies_ms.append((time.perf_counter() - sent) * 1000)
            served.statuses.append(response.status_code)
    await asyncio.gather(*pending)
    await upstream.aclose()
    return served
