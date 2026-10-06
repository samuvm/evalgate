"""Paired bootstrap of a metric difference over the same cases (docs/CONTRACTS/retrieval-metrics.md §4).

**Cases are resampled, never runs.** Each replicate draws n cases with replacement and takes the mean of
`head - base` over those same cases. The cases of a golden set differ from each other far more than a change
moves any one of them; pairing removes that spread from the difference, which is why it detects changes an
unpaired bootstrap buries (R8). There is no unpaired bootstrap in this repository, and two runs over different
cases raise instead of degrading into one.

Deterministic by construction (G-DETERMINISM): the seed is an argument, the cases are put in sorted order
before any draw, and sums use `math.fsum`. The same inputs give the same bits on any machine.

Standard library only, on purpose: 10,000 replicates over 200 cases take about half a second, and numpy and
scipy would be two more pinned dependencies to audit for that (ADR-014).
"""

import math
import random
from collections.abc import Mapping
from dataclasses import dataclass
from fractions import Fraction


class CaseMismatch(ValueError):
    """The two runs were not measured over the same cases. Nothing is compared: there is no pair."""


@dataclass(frozen=True, slots=True)
class Bootstrap:
    n: int
    replicates: int
    delta: float  # mean(head) - mean(base), over the same cases
    ci_low: float
    ci_high: float
    # Share of the replicates in which head was NOT worse than base (delta* >= 0). Exact: a count over B.
    not_worse: Fraction


def _named(cases: set[str]) -> str:
    listed = sorted(cases)
    return ", ".join(listed[:5]) + (f" y {len(listed) - 5} más" if len(listed) > 5 else "")


def paired_bootstrap(
    base: Mapping[str, float], head: Mapping[str, float], *, replicates: int, seed: int, level: Fraction
) -> Bootstrap:
    """Percentile interval at `level` for mean(head) - mean(base), resampling the cases both runs share.

    The interval ends are RANKS of the sorted replicates, chosen so that `ci_high < 0` holds exactly when
    `not_worse <= (1 - level) / 2`: the report shows the interval and the gate decides on the count, and the
    two can never tell different stories. The ranks are also symmetric, so swapping the runs mirrors the
    result to the last bit.
    """
    if replicates < 1:
        raise ValueError(f"replicates must be at least 1, not {replicates}")
    if not 0 < level < 1:
        raise ValueError(f"level must be strictly between 0 and 1, not {level}")
    if base.keys() != head.keys():
        only_base, only_head = set(base) - set(head), set(head) - set(base)
        raise CaseMismatch(
            f"the runs do not share their cases: only in base [{_named(only_base)}], "
            f"only in head [{_named(only_head)}]"
        )
    if not base:
        raise ValueError("no cases to compare")

    diffs = [head[case] - base[case] for case in sorted(base)]
    n = len(diffs)
    rng = random.Random(seed)  # noqa: S311  # nosec B311 - resampling for statistics, not cryptography
    means = sorted(math.fsum(rng.choices(diffs, k=n)) / n for _ in range(replicates))

    alpha = (1 - level) / 2
    low_rank = math.floor(replicates * alpha) + 1  # 1-based, and low_rank + high_rank == replicates + 1
    high_rank = math.ceil(replicates * (1 - alpha))
    return Bootstrap(
        n=n,
        replicates=replicates,
        delta=math.fsum(diffs) / n,
        ci_low=means[low_rank - 1],
        ci_high=means[high_rank - 1],
        not_worse=Fraction(sum(mean >= 0 for mean in means), replicates),
    )
