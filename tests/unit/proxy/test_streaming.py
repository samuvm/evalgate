"""Corpus-driven TDD of `proxy/streaming.py` (RULES §4.2 punto 3): one test per file of
`tests/fixtures/sse/`, and between them the 12 edge cases that `PLAN.md` §3 fixes for F2.

The invariant under test is R2: **the accounting always closes**. Whatever ends the stream — the client
hanging up, the provider cutting, a timeout, a malformed frame, an error body, or nothing at all — exactly
one usage record comes out, and it never claims fewer tokens than were actually emitted. Those tokens are
already paid for.

The tokenizer is injected (`words`): this module is pure and brings none of its own.
"""

import asyncio
import json
from collections.abc import AsyncIterator
from pathlib import Path

import pytest

from evalgate.proxy.streaming import (
    END_CLIENT_DISCONNECT,
    END_DONE,
    END_ERROR,
    END_TIMEOUT,
    END_UPSTREAM_EOF,
    SOURCE_ESTIMATED,
    SOURCE_PROVIDER,
    StreamAccountant,
    Usage,
    UsageRecord,
    relay,
)

CORPUS = Path(__file__).resolve().parents[2] / "fixtures" / "sse"
TEXT = "El precio es 42."
PROVIDER_USAGE = Usage(input_tokens=15, output_tokens=6, source=SOURCE_PROVIDER)


def words(text: str) -> int:
    """Deterministic stub tokenizer. The real one is injected by whoever mounts the proxy."""
    return len(text.split())


def transcript(name: str) -> bytes:
    return (CORPUS / name).read_bytes()


def frames(raw: bytes) -> list[bytes]:
    """Split a transcript into SSE frames, separator included: what a provider puts on the wire per write."""
    return [piece + b"\n\n" for piece in raw.split(b"\n\n") if piece]


def consume(
    name: str,
    *,
    size: int | None = None,
    stop_after: int | None = None,
    fail_with: BaseException | None = None,
) -> tuple[bytes, list[UsageRecord]]:
    """Drive `relay` over one fixture and return what reached the client and what got recorded.

    `size` slices the transcript in fixed byte blocks (frame by frame when it is None), `stop_after` hangs
    up after that many pieces, and `fail_with` is raised by the provider once the transcript runs out.
    """
    raw = transcript(name)
    records: list[UsageRecord] = []
    accountant = StreamAccountant(count_tokens=words)

    async def source() -> AsyncIterator[bytes]:
        pieces = frames(raw) if size is None else [raw[i : i + size] for i in range(0, len(raw), size)]
        for piece in pieces:
            yield piece
        if fail_with is not None:
            raise fail_with

    async def run() -> bytes:
        forwarded = bytearray()
        stream = relay(source(), accountant, records.append)
        try:
            async for piece in stream:
                forwarded += piece
                if stop_after is not None and len(forwarded.split(b"\n\n")) > stop_after:
                    await stream.aclose()  # the client hung up
                    break
        except BaseException as exc:  # the fixture decides which one; the test asserts it
            if fail_with is None or type(exc) is not type(fail_with):
                raise
        return bytes(forwarded)

    return asyncio.run(run()), records


def only(records: list[UsageRecord]) -> UsageRecord:
    assert len(records) == 1, f"R2: exactly one usage record, got {len(records)}"
    return records[0]


def test_01_client_disconnect_records_the_tokens_already_emitted() -> None:
    forwarded, records = consume("01-client-disconnect.sse", stop_after=3)

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=2, source=SOURCE_ESTIMATED),
        text="El precio ",
        chunks=3,
        finish_reason=None,
        end=END_CLIENT_DISCONNECT,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )
    assert forwarded == b"".join(frames(transcript("01-client-disconnect.sse"))[:3])


def test_02_upstream_cutoff_is_not_a_finished_stream() -> None:
    _, records = consume("02-upstream-cutoff.sse")

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=2, source=SOURCE_ESTIMATED),
        text="El precio ",
        chunks=3,
        finish_reason=None,
        end=END_UPSTREAM_EOF,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_03_a_malformed_frame_is_forwarded_verbatim_and_does_not_stop_the_accounting() -> None:
    raw = transcript("03-malformed-chunk.sse")
    forwarded, records = consume("03-malformed-chunk.sse")

    assert forwarded == raw, "passthrough: the proxy does not repair the provider's frames"
    assert only(records) == UsageRecord(
        usage=PROVIDER_USAGE,
        text=TEXT,
        chunks=7,
        finish_reason="stop",
        end=END_DONE,
        malformed=1,
        model="qwen3.5:4b-mlx",
    )


def test_04_a_timeout_midstream_still_closes_the_accounting() -> None:
    _, records = consume("04-timeout-midstream.sse", fail_with=TimeoutError())

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=2, source=SOURCE_ESTIMATED),
        text="El precio ",
        chunks=3,
        finish_reason=None,
        end=END_TIMEOUT,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_05_without_a_usage_chunk_the_tokens_are_estimated_from_the_text() -> None:
    _, records = consume("05-missing-usage-chunk.sse")

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=4, source=SOURCE_ESTIMATED),
        text=TEXT,
        chunks=6,
        finish_reason="stop",
        end=END_DONE,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_06_an_explicit_usage_null_is_not_zero_tokens() -> None:
    _, records = consume("06-done-without-usage.sse")

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=4, source=SOURCE_ESTIMATED),
        text=TEXT,
        chunks=7,
        finish_reason="stop",
        end=END_DONE,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_07_a_character_split_between_network_chunks_survives_reassembly() -> None:
    raw = transcript("07-unicode-split.sse")
    forwarded, records = consume("07-unicode-split.sse", size=1)

    assert forwarded == raw
    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=15, output_tokens=7, source=SOURCE_PROVIDER),
        text="El año cuesta 42 € 🙂",
        chunks=6,
        finish_reason="stop",
        end=END_DONE,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_08_keep_alives_are_neither_text_nor_malformed_frames() -> None:
    raw = transcript("08-keepalive-empty.sse")
    forwarded, records = consume("08-keepalive-empty.sse")

    assert forwarded == raw, "a keep-alive reaches the client: it is what holds the connection open"
    assert only(records) == UsageRecord(
        usage=PROVIDER_USAGE,
        text=TEXT,
        chunks=7,
        finish_reason="stop",
        end=END_DONE,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_09_an_error_body_midstream_closes_the_accounting_as_an_error() -> None:
    _, records = consume("09-error-midstream.sse")

    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=2, source=SOURCE_ESTIMATED),
        text="El precio ",
        chunks=3,
        finish_reason=None,
        end=END_ERROR,
        malformed=0,
        model="qwen3.5:4b-mlx",
    )


def test_10_a_second_done_does_not_open_a_second_record() -> None:
    _, records = consume("10-double-done.sse")

    assert only(records).end == END_DONE
    assert only(records).usage == PROVIDER_USAGE


def test_11_an_unexpected_finish_reason_is_recorded_as_it_came() -> None:
    _, records = consume("11-unexpected-finish-reason.sse")

    assert only(records).finish_reason == "guardrail_intervened"
    assert only(records).end == END_DONE


def test_12_a_zero_length_stream_still_emits_its_record() -> None:
    forwarded, records = consume("12-zero-length-stream.sse")

    assert forwarded == b""
    assert only(records) == UsageRecord(
        usage=Usage(input_tokens=0, output_tokens=0, source=SOURCE_ESTIMATED),
        text="",
        chunks=0,
        finish_reason=None,
        end=END_UPSTREAM_EOF,
        malformed=0,
    )


REASONING = "13-reasoning-tokens.sse"


def reasoning_sent(raw: bytes, frames_taken: int) -> str:
    """The `delta.reasoning` the provider put in those frames, read from the transcript by the test itself.

    The test does not ask the code under test what was sent: it reads the bytes, which is the only way an
    assertion about token accounting proves anything.
    """
    thought = ""
    for frame in [piece for piece in raw.split(b"\n\n") if piece][:frames_taken]:
        payload = frame[len(b"data: ") :].strip()
        if payload == b"[DONE]":
            continue
        for choice in json.loads(payload).get("choices") or []:
            thought += (choice.get("delta") or {}).get("reasoning") or ""
    return thought


def test_13_a_reasoning_model_bills_what_never_reaches_content() -> None:
    """Extra al corpus de PLAN §3, con transcripción REAL de Ollama (ver CASES.yaml).

    `delta.reasoning` trae 16 palabras de razonamiento, `delta.content` va vacío, y el proveedor factura
    40 tokens de completion. El texto de la respuesta y lo que se paga no son lo mismo.
    """
    _, records = consume(REASONING)
    record = only(records)

    assert record.text == ""
    assert record.usage == Usage(input_tokens=18, output_tokens=40, source=SOURCE_PROVIDER)
    assert record.reasoning == reasoning_sent(transcript(REASONING), 35)


def test_13_a_reasoning_stream_cut_before_usage_still_counts_what_was_thought() -> None:
    """Lo que de verdad se paga: si el cliente cuelga antes del chunk de `usage`, la estimación tiene que
    contar el razonamiento. Contando solo `content`, un corte registra 0 tokens de algo ya facturado."""
    thought = reasoning_sent(transcript(REASONING), 20)
    _, records = consume(REASONING, stop_after=20)
    record = only(records)

    assert record.usage.source == SOURCE_ESTIMATED
    assert record.usage.output_tokens == words(thought) > 0
    assert record.reasoning == thought


def test_every_file_of_the_corpus_has_a_test_in_this_module() -> None:
    """RULES §4.2 punto 3. `scripts/rules/sse_corpus_coverage.py` lo comprueba en el gate; aquí se ve."""
    covered = {name[5:7] for name in globals() if name.startswith("test_") and name[5:7].isdigit()}

    assert {path.name[:2] for path in CORPUS.glob("*.sse")} == covered


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.sse")), ids=lambda p: p.name)
def test_the_proxy_never_invents_tokens_it_did_not_see(path: Path) -> None:
    """The floor of R2: whatever happened, the record never claims less than the text it forwarded."""
    _, records = consume(path.name)
    record = only(records)

    assert record.usage.output_tokens >= words(record.text)


@pytest.mark.parametrize("path", sorted(CORPUS.glob("*.sse")), ids=lambda p: p.name)
def test_every_record_names_the_model_that_actually_answered(path: Path) -> None:
    """F3: the span carries `response.model`, and a stream only says it inside its chunks. Every fixture was
    answered by the same model; the zero-length stream never said who it was, and that is `None`, not a
    guess from the request."""
    _, records = consume(path.name)
    declared = b'"model":"qwen3.5:4b-mlx"' in transcript(path.name)

    assert only(records).model == ("qwen3.5:4b-mlx" if declared else None)


def test_the_first_chunk_with_text_is_stamped_by_the_injected_clock() -> None:
    """TTFT (docs/bench/protocol.md §6) ends at the first chunk WITH CONTENT: the role-only opening chunk
    of fixture 01 carries `content: ""` and does not count. The clock is injected, like the tokenizer:
    this module stays pure."""
    ticks = iter(range(100, 200))
    accountant = StreamAccountant(count_tokens=words, clock=lambda: next(ticks))
    opening, first_text, *_ = frames(transcript("01-client-disconnect.sse"))

    accountant.feed(opening)
    accountant.feed(first_text)

    assert accountant.result(END_DONE).first_content_ns == 101


def test_thinking_is_content_for_the_first_token_clock() -> None:
    """A reasoning model's first token is a thought. It is generated, billed and waited for like any other,
    so it stops the TTFT clock; waiting for `content` would charge the whole reasoning to the proxy."""
    ticks = iter(range(100, 200))
    accountant = StreamAccountant(count_tokens=words, clock=lambda: next(ticks))

    accountant.feed(frames(transcript(REASONING))[0])

    assert accountant.result(END_DONE).first_content_ns == 100


def test_without_a_clock_there_is_no_first_content_time_rather_than_a_made_up_one() -> None:
    _, records = consume("05-missing-usage-chunk.sse")

    assert only(records).first_content_ns is None


# El acumulador, directamente. Estos casos salieron de los mutantes que sobrevivieron a la suite del corpus
# (JOURNAL 2026-09-12): cada uno mata al menos uno, y el primero es además un riesgo real de protocolo.


def accounted(*chunks: bytes, end: str = END_DONE) -> UsageRecord:
    accountant = StreamAccountant(count_tokens=words)
    for chunk in chunks:
        accountant.feed(chunk)
    return accountant.result(end)


def test_two_frames_arriving_in_one_network_chunk_are_both_read() -> None:
    """Nada obliga al proveedor a escribir una trama por paquete: puede mandar varias juntas, y entonces
    quedarse con la última separación perdería todas las anteriores."""
    whole = transcript("05-missing-usage-chunk.sse")
    record = accounted(whole)

    assert (record.text, record.chunks) == (TEXT, 6)


def test_a_frame_with_several_lines_keeps_reading_after_the_ones_it_skips() -> None:
    """SSE permite `event:`, `id:` y comentarios en la MISMA trama que el `data:`. Saltarse una línea no
    puede saltarse la trama entera."""
    frame = (
        b": comentario del proveedor\n"
        b"event: message\n"
        b"id: 42\n"
        b'data: {"choices":[{"index":0,"delta":{"content":"dos palabras"},"finish_reason":null}]}\n\n'
    )

    record = accounted(frame, end=END_UPSTREAM_EOF)

    assert (record.text, record.chunks, record.usage.output_tokens) == ("dos palabras", 1, 2)


def test_every_malformed_frame_is_counted_not_just_the_first() -> None:
    broken = b"data: {roto\n\n"

    assert accounted(broken, broken, broken, end=END_UPSTREAM_EOF).malformed == 3


def test_a_half_written_usage_block_is_not_believed() -> None:
    """Con `prompt_tokens` pero sin `completion_tokens` no hay contabilidad del proveedor: hay media."""
    half = b'data: {"choices":[],"usage":{"prompt_tokens":15}}\n\n'

    record = accounted(b'data: {"choices":[{"delta":{"content":"hola"}}]}\n\n', half)

    assert record.usage == Usage(input_tokens=0, output_tokens=1, source=SOURCE_ESTIMATED)


def test_a_choice_that_is_not_an_object_does_not_hide_the_ones_after_it() -> None:
    mixed = b'data: {"choices":[null,{"index":1,"delta":{"content":"sigo aqui"},"finish_reason":"stop"}]}\n\n'

    record = accounted(mixed)

    assert (record.text, record.finish_reason) == ("sigo aqui", "stop")
