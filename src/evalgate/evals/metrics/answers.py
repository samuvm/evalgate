"""Metrics over the answers of a RAG system. Pure: data in, a number per case out (R11: none calls an LLM;
the judge-based ones receive the judge's verdict as text, already obtained and cached by someone else).

Every metric is PER CASE. The gate resamples cases, so a metric that existed only as an aggregate could not
be compared; and each one is defined on a set of cases fixed by the golden set, never by what the system
answered, so two runs always share their cases and can be paired.

Matching is on whole words, never substrings: "16 meses" does not contain the answer "6 meses".
"""

import re
import unicodedata
from collections.abc import Collection

ABSTENTION = "NO_CONSTA"  # what the system is told to answer when the corpus does not have it
FAITHFUL, UNFAITHFUL = "FIEL", "NO_FIEL"  # the two words the faithfulness judge is told to choose from
_WORD = re.compile(r"[a-z0-9_€$%]+")


def _words(text: str) -> list[str]:
    """Lower-case words without accents. Digits stay whole: `6.073` is `6` and `073`, not `6073`."""
    plain = unicodedata.normalize("NFKD", text.lower())
    return _WORD.findall("".join(char for char in plain if not unicodedata.combining(char)))


def _contains(haystack: list[str], needle: list[str]) -> bool:
    return any(haystack[i : i + len(needle)] == needle for i in range(len(haystack) - len(needle) + 1))


def answer_correct(answer: str, reference: str, excludes: Collection[str] = ()) -> float:
    """1.0 if the answer contains the reference as whole words in order and none of `excludes`, else 0.0.

    For a case with no answer in the corpus the reference IS the abstention word, so the same rule scores
    it: the correct answer there is to say so.

    `excludes` is for questions whose answer is one of several things named in the question ("which is
    heavier, A or B?"): an answer that names both contains the reference and has answered nothing.
    """
    wanted = _words(reference)
    if not wanted:
        raise ValueError("empty reference: a case without a reference answer cannot be scored")
    forbidden = [_words(text) for text in excludes]
    if not all(forbidden):
        raise ValueError("empty exclusion: a case cannot exclude nothing")
    said = _words(answer)
    return float(_contains(said, wanted) and not any(_contains(said, words) for words in forbidden))


def context_recall(retrieved: Collection[str], relevant: Collection[str]) -> float:
    """recall@k = |R ∩ P_k| / |R|, over sets of references (docs/CONTRACTS/retrieval-metrics.md §2)."""
    if not relevant:
        raise ValueError("no relevant references: negative cases stay out of the recall denominator")
    return len(set(relevant) & set(retrieved)) / len(set(relevant))


def abstained(answer: str) -> float:
    """1.0 if the system declined to answer. Over positive cases its mean is the incorrect-abstention rate."""
    return float(_contains(_words(answer), _words(ABSTENTION)))


def _verdict(text: str) -> str | None:
    words = _words(text)
    said_yes, said_no = _words(FAITHFUL)[0] in words, _words(UNFAITHFUL)[0] in words
    if said_yes == said_no:  # neither word, or both: the judge did not decide
        return None
    return FAITHFUL if said_yes else UNFAITHFUL


def faithful(verdict: str) -> float:
    """1.0 only if the judge clearly said the answer is faithful. A verdict nobody can read scores 0.0: a
    rambling judge must not inflate the metric."""
    return float(_verdict(verdict) == FAITHFUL)


def unparseable(verdict: str) -> float:
    """1.0 if the judge's verdict could not be read. Reported on its own: a judge that stops following its
    format should show up as exactly that, not as a drop in faithfulness nobody can explain."""
    return float(_verdict(verdict) is None)
