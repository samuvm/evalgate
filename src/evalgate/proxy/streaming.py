"""Streaming relay and token accounting. Deterministic given a transcript: no I/O beyond the iterator it is
handed, and no tokenizer of its own — whoever mounts the proxy injects one.

R2, the invariant this module exists for: **the accounting always closes.** Every generator here emits its
usage record in a `finally` and survives `asyncio.CancelledError`. A client that hangs up mid-answer has
already paid for the tokens the provider emitted, so those tokens are counted.

Lo que debe hacer está escrito en tests/unit/proxy/test_streaming.py: un test por fichero de
tests/fixtures/sse/, y entre ellos los 12 casos límite de PLAN.md §3 (RULES §4.2 punto 3).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from typing import Any

_FRAME_END = b"\n\n"
_DATA = b"data:"
_DONE = b"[DONE]"

# How the stream ended. `done` and `error` are what the transcript said; the other three, what the transport
# saw. They are not interchangeable: only `done` means the provider finished what it was paid for.
END_DONE = "done"
END_UPSTREAM_EOF = "upstream_eof"
END_CLIENT_DISCONNECT = "client_disconnect"
END_TIMEOUT = "timeout"
END_ERROR = "error"

# Where the token count comes from. `provider` is its `usage` block, `estimated` the injected tokenizer over
# the reassembled text. The report says which: an estimate published as an exact number is a lie.
SOURCE_PROVIDER = "provider"
SOURCE_ESTIMATED = "estimated"


@dataclass(frozen=True, slots=True)
class Usage:
    input_tokens: int
    output_tokens: int
    source: str


@dataclass(frozen=True, slots=True)
class UsageRecord:
    usage: Usage
    text: str
    chunks: int
    finish_reason: str | None
    end: str
    malformed: int
    # The answer and what it cost are not the same text. A reasoning model puts its thinking in
    # `delta.reasoning`, leaves `delta.content` empty and bills the thinking all the same, so it is counted
    # and kept apart: mixing it into `text` would put the model's scratchpad in the answer.
    reasoning: str = ""
    # The model that ANSWERED, as the stream itself said it: providers alias and reroute, so the request's
    # model is not evidence of who spoke. `None` when no chunk said it; never a guess from the request.
    model: str | None = None
    # When the first chunk carrying generated text (answer or thought) arrived, by the injected clock. The
    # end of TTFT (docs/bench/protocol.md §6). `None` without a clock or without such a chunk.
    first_content_ns: int | None = None


class StreamAccountant:
    """Accumulates the SSE bytes the proxy forwards and turns them into exactly one usage record."""

    def __init__(
        self,
        count_tokens: Callable[[str], int],
        input_tokens: int = 0,
        clock: Callable[[], int] | None = None,
    ) -> None:
        self._count_tokens = count_tokens
        self._clock = clock
        self._arrived: int | None = None  # clock reading of the bytes being read right now
        self._first_content_ns: int | None = None
        self._model: str | None = None
        self._input_tokens = input_tokens
        self._pending = bytearray()
        self._parts: list[str] = []
        self._thoughts: list[str] = []
        self._chunks = 0
        self._malformed = 0
        self._finish_reason: str | None = None
        self._provider_usage: tuple[int, int] | None = None
        self._done = False
        self._error = False

    def feed(self, data: bytes) -> None:
        """Account for the bytes just forwarded.

        Framing happens on BYTES and decoding comes after: the provider writes when it feels like it, and a
        multi-byte character (or a whole frame) can arrive split in two. Decoding each network chunk on its
        own would corrupt the text and is the bug that fixture 07 exists to catch.
        """
        if self._clock is not None and self._first_content_ns is None:
            # Stamped on ARRIVAL, before framing: a frame split across two writes arrived with the second.
            self._arrived = self._clock()
        self._pending += data
        while (cut := self._pending.find(_FRAME_END)) != -1:
            frame = bytes(self._pending[:cut])
            del self._pending[: cut + len(_FRAME_END)]
            self._read(frame)

    def result(self, end: str) -> UsageRecord:
        """The record to emit. `end` is what the transport saw; what the stream itself said wins over it."""
        text, reasoning = "".join(self._parts), "".join(self._thoughts)
        if self._provider_usage is not None:
            usage = Usage(*self._provider_usage, source=SOURCE_PROVIDER)
        else:
            # Counted separately and added, not concatenated: they are two streams of tokens, and joining
            # them would glue the last word of one to the first of the other.
            emitted = self._count_tokens(text) + self._count_tokens(reasoning)
            usage = Usage(self._input_tokens, emitted, SOURCE_ESTIMATED)
        return UsageRecord(
            usage,
            text,
            self._chunks,
            self._finish_reason,
            self._ended(end),
            self._malformed,
            reasoning,
            self._model,
            self._first_content_ns,
        )

    def _ended(self, transport: str) -> str:
        """An error the provider announced, or a `[DONE]` it sent, say more than how the socket closed."""
        if self._error:
            return END_ERROR
        if self._done:
            return END_DONE
        return transport

    def _read(self, frame: bytes) -> None:
        for line in frame.split(b"\n"):
            if not line or line.startswith(b":"):
                continue  # `: ping` keep-alive comment
            if not line.startswith(_DATA):
                continue  # event:/id:/retry: carry no payload to account for
            payload = line[len(_DATA) :].strip()
            if not payload:
                continue  # `data:` with nothing in it: keep-alive too, not a malformed frame
            if payload == _DONE:
                self._done = True
                continue
            try:
                event = json.loads(payload)
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._malformed += 1
                continue
            if not isinstance(event, dict):
                self._malformed += 1
                continue
            self._account(event)

    def _account(self, event: dict[str, Any]) -> None:
        if self._model is None and isinstance(model := event.get("model"), str):
            self._model = model  # the first one said; a stream does not change speakers halfway
        if "error" in event:
            self._error = True
            return
        self._chunks += 1
        usage = event.get("usage")
        if isinstance(usage, dict):
            # `usage: null` is NOT zero tokens: a provider that never filled it in has told us nothing, and
            # recording a zero would be worse than recording an estimate — it would be recording it wrong.
            prompt, completion = usage.get("prompt_tokens"), usage.get("completion_tokens")
            if isinstance(prompt, int) and isinstance(completion, int):
                self._provider_usage = (prompt, completion)
        choices = event.get("choices")
        for choice in choices if isinstance(choices, list) else []:
            if not isinstance(choice, dict):
                continue
            delta = choice.get("delta")
            if isinstance(delta, dict) and isinstance(content := delta.get("content"), str):
                self._parts.append(content)
                self._generated(content)
            if isinstance(delta, dict) and isinstance(thought := delta.get("reasoning"), str):
                self._thoughts.append(thought)
                self._generated(thought)
            if isinstance(finish := choice.get("finish_reason"), str):
                self._finish_reason = finish  # recorded as it came, enum of OpenAI or not

    def _generated(self, piece: str) -> None:
        """A thought is generated, billed and waited for like an answer, so it stops the TTFT clock too; the
        role-only opening chunk (`content: ""`) does not."""
        if piece and self._first_content_ns is None:
            self._first_content_ns = self._arrived


async def relay(
    source: AsyncIterator[bytes],
    accountant: StreamAccountant,
    record: Callable[[UsageRecord], None],
) -> AsyncIterator[bytes]:
    """Forward the provider's stream chunk by chunk while `accountant` counts in parallel.

    The `finally` is R2 and is not optional: it runs on `GeneratorExit` (the client hung up), on
    `CancelledError` (its task was cancelled) and on any provider failure.
    """
    end = END_UPSTREAM_EOF
    try:
        async for chunk in source:
            accountant.feed(chunk)
            yield chunk
    except (GeneratorExit, asyncio.CancelledError):
        end = END_CLIENT_DISCONNECT
        raise
    except TimeoutError:
        end = END_TIMEOUT
        raise
    finally:
        record(accountant.result(end))
