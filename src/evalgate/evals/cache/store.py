"""The recorded cache of model calls: a JSONL file of answers, keyed by `cache_key`.

This file is what makes `make eval` deterministic and free: the suite reads recorded answers instead of
calling a model, so a second run costs nothing and says the same (G-CACHE-HIT, G-DETERMINISM). It lives in
the repository and is reviewed in diffs, so it is plain text: one JSON object per line, appended in call
order.

**An entry is never overwritten with a different answer.** At temperature 0 the same call gives the same
answer; if it one day does not, keeping the newest silently would hide exactly the non-determinism this
project exists to make visible. So that is an error, with the key.

"Cost" here is tokens, not euros: with local models every euro is zero (contract pricing-table §4) and a
ratio of zeros says nothing. Tokens are what a paid provider would bill, and what the run avoided.
"""

import json
from dataclasses import asdict, dataclass
from pathlib import Path


class CacheCorrupt(ValueError):
    """The cache file cannot be trusted: unreadable line, or two different answers under one key."""


@dataclass(frozen=True, slots=True)
class Entry:
    key: str
    answer: str  # what the model said, verbatim
    input_tokens: int
    output_tokens: int

    @property
    def tokens(self) -> int:
        return self.input_tokens + self.output_tokens


@dataclass(frozen=True, slots=True)
class CacheStats:
    hits: int
    misses: int
    spent_tokens: int  # tokens of the calls that had to be made (the misses, once recorded)
    saved_tokens: int  # tokens of the calls that were not made (the hits)

    @property
    def marginal_cost_ratio(self) -> float:
        """What this run cost over what it would have cost with no cache. 1.0 cold, 0.0 fully warm."""
        total = self.spent_tokens + self.saved_tokens
        return self.spent_tokens / total if total else 0.0

    @property
    def hit_rate(self) -> float:
        asked = self.hits + self.misses
        return self.hits / asked if asked else 0.0


def _entry(line: str, number: int, path: Path) -> Entry:
    try:
        node = json.loads(line)
        entry = Entry(node["key"], node["answer"], node["input_tokens"], node["output_tokens"])
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise CacheCorrupt(f"{path.name} línea {number}: entrada ilegible ({type(exc).__name__})") from None
    if not (isinstance(entry.key, str) and isinstance(entry.answer, str)) or not all(
        isinstance(count, int) and not isinstance(count, bool) for count in (entry.input_tokens, entry.output_tokens)
    ):
        raise CacheCorrupt(f"{path.name} línea {number}: entrada con tipos que no corresponden")
    return entry


class ModelCache:
    """Answers recorded in `path`, with the count of what this run found and what it had to pay for."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._entries: dict[str, Entry] = {}
        self._hits = self._misses = self._spent = self._saved = 0
        if not path.exists():
            return
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if not line.strip():
                continue
            entry = _entry(line, number, path)
            if self._entries.get(entry.key, entry) != entry:
                raise CacheCorrupt(f"{path.name} línea {number}: segunda respuesta distinta para {entry.key[:8]}…")
            self._entries[entry.key] = entry

    def get(self, key: str) -> Entry | None:
        """The recorded answer, or `None` when the call has to be made. Either way it is counted."""
        entry = self._entries.get(key)
        if entry is None:
            self._misses += 1
        else:
            self._hits += 1
            self._saved += entry.tokens
        return entry

    def put(self, entry: Entry) -> None:
        """Record the answer of a call that was just made, and count its cost as spent by this run."""
        known = self._entries.get(entry.key)
        if known is not None:
            if known != entry:
                raise CacheCorrupt(
                    f"{self.path.name}: otra respuesta para la clave {entry.key[:8]}…; una entrada no se pisa"
                )
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(asdict(entry), ensure_ascii=False, separators=(",", ":")) + "\n")
        self._entries[entry.key] = entry
        self._spent += entry.tokens

    def stats(self) -> CacheStats:
        return CacheStats(self._hits, self._misses, self._spent, self._saved)
