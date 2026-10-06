"""The cache key of a model call (R10).

A cached judgement is only worth reusing if NOTHING that could change it has changed. So the key is made of
all of it: who asks (role and id), which model, with which sampling parameters, with which version and bytes
of the prompt, about exactly which text. Change any one and it is another call; change none and it is the
same call, however the configuration happened to be written.

Two ways of getting this wrong, both silent, both tested in tests/unit/judges/test_cache_key.py:
- forgetting a component: the cache serves the judgement of the OLD prompt and the metric keeps its old value;
- concatenating components: ("ab", "c") and ("a", "bc") become the same key. Canonical JSON keeps each
  value in its own field, so there is nothing to bleed.

The key is a sha256 of that canonical form. It is not reversible and holds nothing of the text.
"""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelCall:
    """Everything that can change what a model answers. Change any of it and it is another call."""

    role: str  # "judge" | "generator": two roles never share an entry, even with everything else equal
    caller_id: str  # the judge's id, or the generator's
    model: str
    sampling: Mapping[str, float | int | str]  # temperature, seed, max_tokens…
    prompt_version: int
    prompt_sha256: str
    text_sha256: str  # of the exact text sent: what is judged, or the filled-in prompt


def text_digest(text: str) -> str:
    """sha256 of the exact text, byte for byte in UTF-8. No trimming, no normalising: a trailing space is
    another prompt as far as a model is concerned."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _number(value: float | int | str) -> float | str:
    # 0 and 0.0 ask the model for the same thing; True is not a number here.
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else str(value)


def cache_key(call: ModelCall) -> str:
    """The key under which this call's answer is stored: sha256 of the canonical JSON of its components."""
    canonical = json.dumps(
        {
            "role": call.role,
            "caller_id": call.caller_id,
            "model": call.model,
            "sampling": {name: _number(value) for name, value in call.sampling.items()},
            "prompt_version": call.prompt_version,
            "prompt_sha256": call.prompt_sha256,
            "text_sha256": call.text_sha256,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
