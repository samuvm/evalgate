"""The recorded cache: what `make eval` reads so that a second run costs nothing and says the same.

It is a file that goes into the repository, so it has two jobs: remember answers, and refuse to remember
them wrong. An entry is never overwritten with a different answer: at temperature 0 the same call gives the
same answer, and if it did not, silently keeping the newest would hide exactly the non-determinism the
project needs to see.
"""

from pathlib import Path

import pytest

from evalgate.evals.cache.store import CacheCorrupt, CacheStats, Entry, ModelCache

A = Entry(key="a" * 64, answer="sí, es fiel", input_tokens=120, output_tokens=8)
B = Entry(key="b" * 64, answer="no", input_tokens=200, output_tokens=2)


def test_an_empty_cache_misses_and_counts_it(tmp_path: Path) -> None:
    cache = ModelCache(tmp_path / "cache.jsonl")

    assert cache.get(A.key) is None
    assert cache.stats() == CacheStats(hits=0, misses=1, spent_tokens=0, saved_tokens=0)


def test_what_is_put_is_got_back_verbatim_and_counted_as_a_hit(tmp_path: Path) -> None:
    cache = ModelCache(tmp_path / "cache.jsonl")
    cache.put(A)

    assert cache.get(A.key) == A
    assert cache.stats().hits == 1


def test_the_cache_survives_the_process_that_wrote_it(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    first = ModelCache(path)
    first.put(A)
    first.put(B)

    again = ModelCache(path)

    assert (again.get(A.key), again.get(B.key)) == (A, B)


def test_a_cold_run_spends_everything_and_a_warm_one_nothing(tmp_path: Path) -> None:
    """The goal's own sentence (G-CACHE-HIT): the second run costs <= 5 % of the first. Here, exactly 0."""
    path = tmp_path / "cache.jsonl"
    cold = ModelCache(path)
    for entry in (A, B):
        assert cold.get(entry.key) is None  # miss: the call has to be made…
        cold.put(entry)  # …and its cost is spent
    warm = ModelCache(path)
    for entry in (A, B):
        assert warm.get(entry.key) == entry

    assert cold.stats() == CacheStats(hits=0, misses=2, spent_tokens=330, saved_tokens=0)
    assert warm.stats() == CacheStats(hits=2, misses=0, spent_tokens=0, saved_tokens=330)
    assert (cold.stats().marginal_cost_ratio, warm.stats().marginal_cost_ratio) == (1.0, 0.0)
    assert (cold.stats().hit_rate, warm.stats().hit_rate) == (0.0, 1.0)


def test_a_partly_warm_run_costs_its_share(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    ModelCache(path).put(A)  # 128 tokens already paid for
    run = ModelCache(path)
    assert run.get(A.key) == A
    assert run.get(B.key) is None
    run.put(B)  # 202 tokens spent now

    stats = run.stats()

    assert (stats.spent_tokens, stats.saved_tokens) == (202, 128)
    assert stats.marginal_cost_ratio == pytest.approx(202 / 330)
    assert stats.hit_rate == 0.5


def test_a_run_that_asked_nothing_has_no_ratio_to_boast_about(tmp_path: Path) -> None:
    stats = ModelCache(tmp_path / "cache.jsonl").stats()

    assert (stats.marginal_cost_ratio, stats.hit_rate) == (0.0, 0.0)


def test_putting_the_same_entry_again_is_harmless_and_writes_nothing(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    cache = ModelCache(path)
    cache.put(A)
    size = path.stat().st_size

    cache.put(A)

    assert path.stat().st_size == size


def test_a_different_answer_under_the_same_key_is_refused_not_overwritten(tmp_path: Path) -> None:
    cache = ModelCache(tmp_path / "cache.jsonl")
    cache.put(A)

    with pytest.raises(CacheCorrupt, match="aaaaaaaa"):
        cache.put(Entry(A.key, "no, no es fiel", 120, 8))
    assert cache.get(A.key) == A


@pytest.mark.parametrize(
    "line",
    ["{esto no es json", '{"key": "k"}', '{"key": "k", "answer": 3, "input_tokens": 1, "output_tokens": 1}', "[]"],
)
def test_a_cache_file_with_a_line_it_cannot_read_is_refused_with_the_line_number(tmp_path: Path, line: str) -> None:
    path = tmp_path / "cache.jsonl"
    ModelCache(path).put(A)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")

    with pytest.raises(CacheCorrupt, match="línea 2"):
        ModelCache(path)


def test_a_file_holding_two_answers_for_one_key_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "cache.jsonl"
    ModelCache(path).put(A)
    text = path.read_text("utf-8")
    path.write_text(text + text.replace("sí, es fiel", "no"), "utf-8")

    with pytest.raises(CacheCorrupt, match="línea 2"):
        ModelCache(path)


def test_the_file_is_one_json_object_per_line_with_unicode_kept_readable(tmp_path: Path) -> None:
    """It is reviewed in diffs: one entry per line, appended in call order, accents as accents."""
    path = tmp_path / "nested" / "cache.jsonl"
    cache = ModelCache(path)
    cache.put(A)
    cache.put(B)

    lines = path.read_text("utf-8").splitlines()

    assert len(lines) == 2
    assert "sí, es fiel" in lines[0]
    assert lines[0].startswith('{"key":"' + "a" * 64)
