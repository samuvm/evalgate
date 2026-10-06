"""Answer a model call from the recorded cache, or make it.

The one rule: **a recorded run never calls a model.** `make eval` runs in the gate, offline, and must give
the same report on any machine; if it needs a call that is not recorded, the cache and the suite have
drifted apart and the honest thing is to stop and say `make eval-refresh`. Calling the model quietly would
turn a deterministic gate into one that depends on whether Ollama happens to be running.
"""

from collections.abc import Callable

from evalgate.evals.cache.key import ModelCall, cache_key
from evalgate.evals.cache.store import Entry, ModelCache

Live = Callable[[], tuple[str, int, int]]  # makes the call: (answer, input tokens, output tokens)


class CacheMiss(LookupError):
    """A recorded run needed a call that is not recorded. It is not made behind anyone's back."""


def cached_answer(cache: ModelCache, call: ModelCall, live: Live | None) -> str:
    """The answer to `call`: recorded if it is, made with `live` and recorded if it is not.

    `live=None` is a recorded run: a miss raises `CacheMiss`.
    """
    key = cache_key(call)
    recorded = cache.get(key)
    if recorded is not None:
        return recorded.answer
    if live is None:
        raise CacheMiss(
            f"{call.role} {call.caller_id} ({call.model}): llamada no grabada en {cache.path.name}. "
            "La suite y la caché no coinciden: `make eval-refresh` la recalcula, fuera del gate."
        )
    answer, input_tokens, output_tokens = live()
    cache.put(Entry(key, answer, input_tokens, output_tokens))
    return answer
