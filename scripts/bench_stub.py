"""Deterministic loopback upstream for `make bench` (docs/bench/protocol.md §1). Not a provider: a clock.

- non-streaming: answers after exactly 50 ms with a `chat.completion` valid against the pinned OpenAPI
  (logprobs and refusal included, so the proxy has nothing to normalize and the arms do the same work);
- streaming: first chunk at 50 ms, then one chunk every 10 ms, 64 chunks, the `usage` chunk and `[DONE]`.

Usage: python scripts/bench_stub.py --port N
"""

import argparse
import asyncio
import json
from collections.abc import AsyncIterator

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

FIRST_S, EVERY_S, CHUNKS = 0.050, 0.010, 64
MODEL = "bench-stub"

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def chunk(delta: dict[str, str], finish: str | None = None) -> bytes:
    event = {
        "id": "bench",
        "object": "chat.completion.chunk",
        "created": 1,
        "model": MODEL,
        "choices": [{"index": 0, "delta": delta, "logprobs": None, "finish_reason": finish}],
    }
    return b"data: " + json.dumps(event, separators=(",", ":")).encode() + b"\n\n"


async def stream() -> AsyncIterator[bytes]:
    await asyncio.sleep(FIRST_S)
    yield chunk({"role": "assistant", "content": "t0 "})
    for i in range(1, CHUNKS):
        await asyncio.sleep(EVERY_S)
        yield chunk({"content": f"t{i} "}, "stop" if i == CHUNKS - 1 else None)
    usage = {"prompt_tokens": 512, "completion_tokens": CHUNKS, "total_tokens": 512 + CHUNKS}
    yield (
        b"data: "
        + json.dumps(
            {
                "id": "bench",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": MODEL,
                "choices": [],
                "usage": usage,
            }
        ).encode()
        + b"\n\n"
    )
    yield b"data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def completions(request: Request) -> object:
    body = await request.json()
    if body.get("stream") is True:
        return StreamingResponse(stream(), media_type="text/event-stream")
    await asyncio.sleep(FIRST_S)
    return JSONResponse(
        {
            "id": "bench",
            "object": "chat.completion",
            "created": 1,
            "model": MODEL,
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": "ok", "refusal": None},
                    "logprobs": None,
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 512, "completion_tokens": 1, "total_tokens": 513},
        }
    )


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    uvicorn.run(app, host="127.0.0.1", port=parser.parse_args().port, log_level="warning")
