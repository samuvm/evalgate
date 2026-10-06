"""The one place that calls a model for the eval engine. I/O only; excluded from unit tests (RULES §2).

An OpenAI-compatible chat call, the same protocol the proxy speaks. It returns the text and the provider's
own token counts, which is what the cache records as the cost of the call.
"""

from collections.abc import Mapping

import httpx

TIMEOUT_S = 600.0  # a cold 12b model on a shared machine can take minutes to load


def chat(base_url: str, model: str, text: str, sampling: Mapping[str, float | int | str]) -> tuple[str, int, int]:
    """One user message in, (answer, input tokens, output tokens) out. Raises on any non-200."""
    response = httpx.post(
        f"{base_url.rstrip('/')}/chat/completions",
        json={"model": model, "messages": [{"role": "user", "content": text}], "stream": False, **sampling},
        timeout=TIMEOUT_S,
    )
    response.raise_for_status()
    body = response.json()
    usage = body.get("usage") or {}
    message = body["choices"][0]["message"]
    return str(message.get("content") or "").strip(), int(usage["prompt_tokens"]), int(usage["completion_tokens"])
