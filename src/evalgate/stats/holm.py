"""Holm-Bonferroni correction (docs/CONTRACTS/retrieval-metrics.md §4).

Why Holm and not something else, which is the sentence to be able to say out loud: it controls the
FAMILY-WISE error rate, the probability of blocking at least once without cause, and a gate that blocks
without cause gets switched off. It is uniformly more powerful than Bonferroni and assumes nothing about how
the metrics depend on each other, which matters here: quality metrics over the same answers are correlated.

Adjusted p-values instead of adjusted thresholds: "block if adjusted p <= alpha" is then one rule for any
number of metrics, and the report can print the number that decided. Exact arithmetic (`Fraction`), because a
p-value sitting exactly on alpha must fall on the same side on every machine (G-DETERMINISM).
"""

from collections.abc import Sequence
from fractions import Fraction


def holm_adjust(p_values: Sequence[Fraction]) -> list[Fraction]:
    """Holm-adjusted p-values, in the order given.

    Sorted ascending, the i-th smallest (i from 0) is multiplied by `m - i`; the results are made monotone
    (an adjusted value is never below the one before it) and capped at 1. Rejecting where the adjusted value
    is <= alpha is exactly Holm's step-down procedure.
    """
    if any(p < 0 or p > 1 for p in p_values):
        raise ValueError(f"p-value outside [0, 1]: {[str(p) for p in p_values]}")
    m = len(p_values)
    adjusted = [Fraction(0)] * m
    running = Fraction(0)
    for rank, index in enumerate(sorted(range(m), key=lambda i: p_values[i])):
        running = max(running, min(Fraction(1), p_values[index] * (m - rank)))
        adjusted[index] = running
    return adjusted
