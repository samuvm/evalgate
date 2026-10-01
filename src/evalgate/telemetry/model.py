"""The internal model of one call to an LLM: `LlmCall`. OUR names, never a single `gen_ai.*` one.

Contract otel-genai §2: the external names are unstable (the whole namespace is in *Development* and has
already broken twice), so the domain speaks its own language and `telemetry/translate.py` is the only
module that knows the pinned one. A break in the spec is then a change in one file, not a migration of the
ClickHouse schema and of every panel.

No field can hold the text of a prompt or of an answer, on purpose (R6): what the model cannot carry, no
exporter can leak.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True, slots=True)
class Cost:
    """What the call cost and WITH WHICH TABLE. Without the table's date a past cost cannot be reproduced."""

    eur: Decimal
    pricing_version: str  # `effective_from` of the pricing/<YYYY-MM-DD>.yaml that priced it


@dataclass(frozen=True, slots=True)
class LlmCall:
    operation: str  # "chat", "embeddings"…
    provider: str  # "ollama", "openai"…: who served it, not how we reached it
    server_address: str
    request_model: str  # what the client asked for
    # What actually answered: providers alias and reroute. `None` only when the provider never said it (a
    # zero-length stream, a hang-up before the first chunk); never taken from the request. PARA-SAMUEL Q-011.
    response_model: str | None
    input_tokens: int
    output_tokens: int
    # "provider" (its `usage` block) or "estimated" (tokenizer over the text). P-005 (a): an estimate that
    # travels without saying so reads as a bill.
    usage_source: str
    finish_reasons: tuple[str, ...]
    started_ns: int  # epoch nanoseconds, the clock OpenTelemetry uses
    ended_ns: int
    # The client hung up mid-stream. Those tokens were paid for all the same, and are counted (R2).
    client_disconnected: bool = False
    temperature: float | None = None
    max_tokens: int | None = None
    error_type: str | None = None
    ttft_ms: float | None = None  # streaming only: request sent → first byte of the first content chunk
    cost: Cost | None = None  # None until pricing exists (F4): an unpriced call is not a free one
