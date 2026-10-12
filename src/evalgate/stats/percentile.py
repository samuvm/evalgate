"""An empirical percentile by nearest rank: the smallest observed value with at least that share at or below.

RULES §5.3: the minimum detectable effect "is not estimated with theory: it is the empirical 95th percentile
of the paired deltas under H0, read directly from the matrix". Read, so no interpolation: the answer is
always a delta that some pair of runs actually showed.
"""

import math
from collections.abc import Sequence
from fractions import Fraction

__all__ = ["empirical_percentile"]


def empirical_percentile(values: Sequence[float], percent: Fraction) -> float:
    """The value of rank ceil(percent/100 · n) among the sorted `values`. `percent` in (0, 100]."""
    if not values:
        raise ValueError("no values to read a percentile from")
    if not 0 < percent <= 100:
        raise ValueError(f"percent must be in (0, 100], not {percent}")
    rank = math.ceil(percent * len(values) / 100)  # exact: `percent` is a Fraction
    return sorted(values)[rank - 1]
