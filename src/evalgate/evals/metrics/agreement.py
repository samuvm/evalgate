"""Agreement between the judge and the human labels: what G-JUDGE-KAPPA publishes. Pure (R11).

The human label is the reference and the judge is what is being measured, so the table keeps the two apart
even though kappa itself is symmetric. A verdict nobody can read is its own label, never dropped: a judge
that stops following its format disagrees with the human on that item, and the number has to say so.
"""

from collections.abc import Mapping
from fractions import Fraction
from typing import Any

from evalgate.evals.metrics.answers import FAITHFUL, UNFAITHFUL, faithful, unparseable
from evalgate.stats.kappa import cohens_kappa

UNREADABLE = "ILEGIBLE"


def judge_label(verdict: str) -> str:
    """The label a judge's raw verdict stands for: FIEL, NO_FIEL or ILEGIBLE. Same reading as the metric."""
    if unparseable(verdict):
        return UNREADABLE
    return FAITHFUL if faithful(verdict) else UNFAITHFUL


def agreement_block(
    ratings: Mapping[str, tuple[str, str]], *, replicates: int, seed: int, level: Fraction
) -> dict[str, Any]:
    """Kappa, its interval and the table behind it, for `ratings` = item -> (human label, judge label).

    Raises what `cohens_kappa` raises: no items, or a single class in which nothing can be measured.
    """
    kappa = cohens_kappa(ratings, replicates=replicates, seed=seed, level=level)
    table: dict[str, dict[str, int]] = {}
    for human, judge in ratings.values():
        row = table.setdefault(human, {})
        row[judge] = row.get(judge, 0) + 1
    agreements = sum(human == judge for human, judge in ratings.values())
    return {
        "point": float(kappa.point),
        "ci95_bootstrap": [float(kappa.ci_low), float(kappa.ci_high)],
        "level": float(level),
        "replicates": kappa.replicates,
        "undefined_replicates": kappa.undefined_replicates,
        "seed": seed,
        "n": kappa.n,
        "raw_agreement": agreements / kappa.n,
        # human label -> judge label -> items. Sorted so the document is the same bytes every time.
        "table_human_judge": {human: dict(sorted(row.items())) for human, row in sorted(table.items())},
        "human_prevalence": {
            human: sum(row.values()) / kappa.n for human, row in sorted(table.items())
        },
    }
