"""G-DISCONNECT y G-TOKENS-STREAM: los dos números de F2 que no se demuestran con ejemplos.

Hypothesis genera el transcript **y** el índice de corte, y el corte se prueba en cada k: es lo que pide
G-DISCONNECT, y es el diferenciador nº 1 del proyecto, porque esos tokens ya están pagados.

Los umbrales se leen de `docs/GOALS.yaml`. Aquí no hay un literal que se pueda ajustar para que el test
pase, que es la segunda regla de oro de la constitución: se puede cambiar cómo se llega al número, nunca
el número.

Qué mide y qué NO mide G-TOKENS-STREAM, dicho sin adornos y desde P-005 (a), aprobada el 2026-09-20: la
exactitud se exige **donde es verificable**, que es el bloque `usage` del proveedor, y ahí el umbral es 0.
Donde no hay `usage` no hay verdad en la sala: el registro viaja declarado como `estimated`, no entra en la
meta, y lo que se publica es `cobertura_usage`, la proporción de casos que sí trajeron el bloque. Medir la
estimación contra el mismo tokenizador que inyecta este test daría 0 por construcción y se leería en el
README como exactitud de facturación que nunca se demostró. Eso es lo que P-005 vino a quitar.

El otro número que P-005 (a) pide —`cobertura_usage`, qué porcentaje de streams trajo el bloque— **no se
publica desde aquí**, y se midió antes de decidirlo: por transcript completo da 0,453 y por índice de corte
0,101 (n=1000 y n=8951, JOURNAL 2026-09-20). El primero es el `st.booleans()` de este generador y el
segundo su reparto de cortes: los dos describen el test, no a los proveedores. Sale con tráfico grabado de
verdad, y hasta entonces no sale (matiz de P-005 en `docs/PARA-SAMUEL.md`).
"""

import asyncio
import json
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

import yaml
from hypothesis import given
from hypothesis import strategies as st
from tests._meter import Meter

from evalgate.proxy.streaming import (
    END_CLIENT_DISCONNECT,
    END_DONE,
    END_UPSTREAM_EOF,
    SOURCE_ESTIMATED,
    SOURCE_PROVIDER,
    StreamAccountant,
    UsageRecord,
    relay,
)

ROOT = Path(__file__).resolve().parents[2]
GOALS: dict[str, Any] = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text(encoding="utf-8"))
UMBRAL: dict[str, Any] = next(m for m in GOALS["metas"] if m["id"] == "G-TOKENS-STREAM")["umbral"]
# El umbral adicional de la meta, leído de GOALS: con `usage` del proveedor, |delta| == 0. Sin literales.
EXACTO: float = next(extra["valor"] for extra in UMBRAL["adicionales"])
DONE = b"data: [DONE]\n\n"
PROMPT_TOKENS = 15


def words(text: str) -> int:
    """The injected tokenizer. Deterministic and irrelevant to what is being measured: it is the same one
    on both sides of the delta, so what is left in the number is the reassembly."""
    return len(text.split())


def frame(payload: dict[str, Any]) -> bytes:
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return b"data: " + body.encode("utf-8") + b"\n\n"


def chunk(delta: dict[str, str] | None = None, finish: str | None = None) -> bytes:
    return frame(
        {
            "id": "chatcmpl-p",
            "object": "chat.completion.chunk",
            "created": 1789045500,
            "model": "qwen3.5:4b-mlx",
            "choices": [{"index": 0, "delta": delta or {}, "finish_reason": finish}],
        }
    )


@st.composite
def transcripts(draw: st.DrawFn) -> tuple[list[bytes], list[str], tuple[int, int] | None]:
    """A stream, the text each of its frames contributes, and the provider's usage if it sends one."""
    pieces = draw(st.lists(st.text(max_size=8), max_size=6))
    with_usage = draw(st.booleans())

    frames = [chunk({"role": "assistant", "content": ""})]
    texts = [""]
    for piece in pieces:
        frames.append(chunk({"content": piece}))
        texts.append(piece)
    frames.append(chunk({}, "stop"))
    texts.append("")

    usage = None
    if with_usage:
        # +3 on purpose: the provider's number must NOT be reproducible by the estimator, or the test would
        # not prove that the `usage` block is what gets recorded when it arrives.
        usage = (PROMPT_TOKENS, words("".join(pieces)) + 3)
        frames.append(
            frame(
                {
                    "id": "chatcmpl-p",
                    "object": "chat.completion.chunk",
                    "created": 1789045500,
                    "model": "qwen3.5:4b-mlx",
                    "choices": [],
                    "usage": {
                        "prompt_tokens": usage[0],
                        "completion_tokens": usage[1],
                        "total_tokens": sum(usage),
                    },
                }
            )
        )
        texts.append("")
    frames.append(DONE)
    texts.append("")

    return frames, texts, usage


def hang_up_after(frames: list[bytes], delivered: int, count: Callable[[str], int]) -> list[UsageRecord]:
    """Pull frames from the provider, deliver `delivered` of them to the client, then hang up.

    `delivered = 0` still pulls one: the chunk already in flight was produced by the provider and is paid
    for, whether or not the client got to see it. That asymmetry is the point of the whole exercise.
    """
    records: list[UsageRecord] = []
    accountant = StreamAccountant(count_tokens=count)

    async def provider() -> AsyncIterator[bytes]:
        for piece in frames:
            yield piece

    async def run() -> None:
        stream = relay(provider(), accountant, records.append)
        pulled = 0
        async for _ in stream:
            pulled += 1
            if pulled >= max(delivered, 1):
                await stream.aclose()
                break

    asyncio.run(run())
    return records


@given(case=transcripts())
def test_disconnect_at_every_index_keeps_the_accounting(
    meter: Meter,
    case: tuple[list[bytes], list[str], tuple[int, int] | None],
) -> None:
    """G-DISCONNECT: for EVERY k there is a usage record, and it never claims fewer tokens than were sent."""
    frames, texts, usage = case

    for cut in range(len(frames) + 1):
        pulled = min(max(cut, 1), len(frames)) if frames else 0
        emitted = "".join(texts[:pulled])
        expected = usage[1] if usage is not None and pulled > frames.index(DONE) - 1 else words(emitted)

        records = hang_up_after(frames, cut, words)

        recorded = records[0].usage.output_tokens if len(records) == 1 else -1
        ok = len(records) == 1 and recorded >= words(emitted) and recorded == expected
        meter.check("G-DISCONNECT", ok)

        assert len(records) == 1, f"R2: the accounting closes even at k={cut}"
        assert records[0].text == emitted
        assert ok, f"k={cut}: recorded {recorded} tokens for {words(emitted)} emitted"


@given(case=transcripts())
def test_token_delta_against_what_the_provider_really_sent(
    meter: Meter,
    case: tuple[list[bytes], list[str], tuple[int, int] | None],
) -> None:
    """G-TOKENS-STREAM (P-005 (a)): exacto donde hay verdad contra la que medir, declarado donde no la hay."""
    frames, texts, usage = case

    for cut in range(len(frames) + 1):
        pulled = min(max(cut, 1), len(frames)) if frames else 0
        saw_usage = usage is not None and pulled > frames.index(DONE) - 1

        record = hang_up_after(frames, cut, words)[0]

        if saw_usage and usage is not None:
            delta = abs(record.usage.output_tokens - usage[1]) / max(usage[1], 1)
            meter.observe("G-TOKENS-STREAM", "delta_con_usage", delta)
            assert record.usage.source == SOURCE_PROVIDER
            assert delta <= EXACTO, f"k={cut}: delta_con_usage={delta:g} frente a {usage[1]}"
        else:
            # Sin `usage` no se compara contra el tokenizador que este test inyectó: es el mismo que usó el
            # contable, el delta sería 0 por construcción y no probaría nada sobre lo que se paga. Lo que sí
            # se exige es que el registro lo DIGA, y que el reensamblado no haya perdido texto.
            assert record.usage.source == SOURCE_ESTIMATED
            assert record.text == "".join(texts[:pulled]), f"k={cut}: el reensamblado perdió texto"


@given(case=transcripts())
def test_the_end_of_the_stream_is_classified_by_what_the_provider_said(
    case: tuple[list[bytes], list[str], tuple[int, int] | None],
) -> None:
    """`[DONE]` beats the transport: how the socket closed says less than what the provider got to say."""
    frames, _, _ = case

    for cut in range(len(frames) + 1):
        pulled = min(max(cut, 1), len(frames)) if frames else 0

        record = hang_up_after(frames, cut, words)[0]

        if not frames:
            assert record.end == END_UPSTREAM_EOF
        elif DONE in frames[:pulled]:
            assert record.end == END_DONE
        else:
            assert record.end == END_CLIENT_DISCONNECT
