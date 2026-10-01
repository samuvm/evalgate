"""H-13 (docs/qa/hallazgos-F2.md): the accounting has to close **inside the request**, not whenever the
garbage collector feels like it.

`tests/property/test_stream_accounting.py` already measures G-DISCONNECT over `relay`, where the test is
the one that closes the generator and the `finally` therefore runs on the spot. That is the module, not the
mounting. Between the relay and the client there is a layer that cancels the task and leaves the response
generator suspended on its `yield`, and a `finally` that exists but runs when the collector wants satisfies
the letter of R2 while losing its invariant: in a long-lived served process the record of a disconnect
comes out at an arbitrary later instant, outside the request that produced it, and does not come out at all
if the process dies first.

So the disconnect is driven here at the **ASGI edge**, which is the only way to pin the cut index exactly:
a `TestClient` reads the whole body before returning and never reproduces the case. The sink is observed at
the instant the ASGI call of that request returns — still inside the event loop, before anything else gets
a chance to finalize pending generators.

P-006 (a), approved on 2026-09-20, put this file inside the command `docs/GOALS.yaml` declares for
G-DISCONNECT. Passing was not enough to honour that: the published `ratio`/`n` come from the meter, so a
file that only passes adds zero cases to the number and the goal would still be reporting the layer that
already worked. Measured before fixing it: the extended command printed `n=208`, exactly what the property
file alone prints. So the cut indices served here are metered too, and the predicate metered is the goal's
own, at the mounting: there is a record when the request returns, AND it never claims fewer tokens than the
provider already emitted.
"""

import asyncio
import gc
from dataclasses import dataclass
from typing import Any

import httpx
import pytest

from evalgate.proxy.app import ProxySettings, create_app, whitespace_tokens
from evalgate.proxy.streaming import (
    END_CLIENT_DISCONNECT,
    END_DONE,
    SOURCE_ESTIMATED,
    SOURCE_PROVIDER,
    UsageRecord,
)
from tests._meter import Meter

from ._paths import ROOT
from ._proxy import UPSTREAM, sse_events

CHAT = "/v1/chat/completions"
BODY = b'{"model":"qwen3.5:4b-mlx","messages":[{"role":"user","content":"precio?"}],"stream":true}'
# The transcript H-13 describes, and the corpus case for this very scenario: five content frames, the
# `finish_reason` frame, the `usage` frame and `[DONE]`.
TRANSCRIPT = (ROOT / "tests" / "fixtures" / "sse" / "01-client-disconnect.sse").read_bytes()
FRAMES = [frame + b"\n\n" for frame in TRANSCRIPT.split(b"\n\n") if frame]


def upstream(frames: list[bytes]) -> httpx.AsyncClient:
    """A provider that writes one frame per network chunk, so the cut index means what it says."""

    def handler(request: httpx.Request) -> httpx.Response:  # noqa: ARG001 · MockTransport's signature
        async def written() -> Any:
            for frame in frames:
                yield frame

        return httpx.Response(200, headers={"content-type": "text/event-stream"}, content=written())

    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


def scope_of(body: bytes) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.1"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": CHAT,
        "raw_path": CHAT.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [
            (b"host", b"testserver"),
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
        ],
        "client": ("127.0.0.1", 51234),
        "server": ("testserver", 80),
    }


@dataclass(frozen=True, slots=True)
class Served:
    """One served request, and the sink read at the two instants that tell `cuándo` from `cuánto`.

    `at_return` is the snapshot taken the moment the ASGI call of that request returned, still inside the
    event loop: it is the only one that answers H-13. `eventually` is the same sink once the loop is gone
    and the collector has run, which is where a record that survives its request ends up showing.
    """

    frames: list[bytes]
    at_return: list[UsageRecord]
    eventually: list[UsageRecord]


def hang_up_after(delivered: int) -> Served:
    """Serve one streaming request and hang up once `delivered` frames have landed on the client.

    `delivered = 0` means no hang-up at all: the control case.
    """
    records: list[UsageRecord] = []
    at_return: list[UsageRecord] = []
    frames: list[bytes] = []

    async def serve() -> None:
        client = upstream(FRAMES)
        settings = ProxySettings(upstream_base_url=UPSTREAM, normalize=False, on_usage=records.append)
        app = create_app(settings, client=client)
        gone, asked = asyncio.Event(), False

        async def receive() -> dict[str, Any]:
            nonlocal asked
            if not asked:
                asked = True
                return {"type": "http.request", "body": BODY, "more_body": False}
            await gone.wait()  # the client stays connected until the test says otherwise
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] != "http.response.body" or not message.get("body"):
                return
            frames.append(message["body"])
            if len(frames) != delivered:
                return
            gone.set()
            # Hand the loop over so the disconnect listener wakes and cancels the response task before the
            # next frame can land. Cancellation then reaches the task inside THIS call, which is exactly
            # the shape H-13 is about: the generator is left suspended on its `yield`, not closed.
            for _ in range(5):
                await asyncio.sleep(0)

        await app(scope_of(BODY), receive, send)
        # Read HERE, before `asyncio.run` shuts the loop down: closing a loop finalizes every pending
        # asynchronous generator, so a sink read after it cannot tell a record emitted by the request from
        # one the runtime rescued afterwards. That difference is the whole finding.
        at_return.extend(records)

    asyncio.run(serve())
    gc.collect()
    return Served(frames, at_return, records)


def delivered_text(frames: list[bytes]) -> tuple[str, bool]:
    """What the client actually saw, and whether the provider's `usage` block was among it."""
    events = sse_events(b"".join(frames))
    text = "".join(
        delta.get("content", "")
        for event in events
        for choice in event.get("choices", [])
        if isinstance(delta := choice.get("delta"), dict)
    )
    return text, any(isinstance(event.get("usage"), dict) for event in events)


@pytest.mark.parametrize("cut", range(1, len(FRAMES)))
def test_the_record_is_out_when_the_request_ends(cut: int) -> None:
    """H-13: exactly one usage record, already emitted when the served request returns."""
    served = hang_up_after(cut)

    assert len(served.frames) == cut, f"the harness delivered {len(served.frames)} frames, not {cut}"
    assert len(served.at_return) == 1, (
        f"R2 at the mounting: cut after {cut} frames left {len(served.at_return)} records when the request "
        f"ended (and {len(served.eventually)} once the runtime finalized what it had abandoned). A record "
        f"that comes out later comes out outside the request that paid for it."
    )


@pytest.mark.parametrize("cut", range(1, len(FRAMES)))
def test_what_the_record_says_after_a_hang_up(meter: Meter, cut: int) -> None:
    """G-DISCONNECT where the request is served: never fewer tokens than the provider already emitted.

    Read from `eventually` on purpose: what the record SAYS is a separate claim from WHEN it comes out, and
    one test that failed for either reason would tell nobody which of the two broke. The METERED predicate
    is the goal's whole one and so reads both snapshots: a record that arrives after its request is not a
    case G-DISCONNECT gets to count, however right its contents turn out to be.
    """
    served = hang_up_after(cut)
    seen, saw_usage = delivered_text(served.frames)

    counted = served.eventually[0].usage.output_tokens if len(served.eventually) == 1 else -1
    meter.check("G-DISCONNECT", len(served.at_return) == 1 and counted >= whitespace_tokens(seen))

    assert len(served.eventually) == 1, f"cut after {cut} frames produced no record at all"
    record = served.eventually[0]
    assert record.end == END_CLIENT_DISCONNECT
    assert record.chunks >= cut - 1, f"cut after {cut} frames accounted only {record.chunks} chunks"
    assert record.text.startswith(seen), f"the record dropped text the client already got: {seen!r}"
    assert record.usage.source == (SOURCE_PROVIDER if saw_usage else SOURCE_ESTIMATED)
    assert record.usage.output_tokens >= whitespace_tokens(seen), (
        f"cut after {cut} frames recorded {record.usage.output_tokens} tokens for {seen!r}: "
        f"those tokens are paid for whether or not the client got to read them"
    )


@pytest.mark.parametrize("cut", range(1, len(FRAMES)))
def test_the_record_is_not_emitted_twice(cut: int) -> None:
    """Closing the stream from the mounting must not add a second record once the collector runs.

    One record too many is the same lie as one too few, and a reference cycle finalized later is how it
    would happen: the check is that the collector finds nothing left to emit.
    """
    served = hang_up_after(cut)

    assert len(served.eventually) == 1, f"cut after {cut} frames ended up with {len(served.eventually)}"


def test_a_stream_nobody_cuts_still_closes_its_accounting() -> None:
    """The control for the harness: with no hang-up the whole transcript lands and the record says `done`.

    Without it the three tests above could pass over a client that never received anything.
    """
    served = hang_up_after(0)

    assert len(served.frames) == len(FRAMES)
    assert len(served.at_return) == 1
    assert (served.at_return[0].end, served.at_return[0].usage.source) == (END_DONE, SOURCE_PROVIDER)
