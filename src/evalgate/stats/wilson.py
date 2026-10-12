"""Wilson's score interval for a proportion: the interval G-GATE-FP publishes next to the false-positive rate.

Wilson and not the textbook `p ± z·sqrt(p(1-p)/n)`: with 0 blocks out of 49 the textbook interval is [0, 0],
which says the gate can never block without cause, and that is the one thing 49 decisions cannot say. Wilson
gives [0, 7.3 %] there, stays inside [0, 1] and holds its coverage for small counts.

Standard library only (ADR-014): the normal quantile is `statistics.NormalDist`.
"""

import math
from fractions import Fraction
from statistics import NormalDist

__all__ = ["wilson_interval"]


def wilson_interval(successes: int, n: int, level: Fraction) -> tuple[float, float]:
    """The two-sided Wilson interval at `level` for `successes` out of `n`, as (low, high)."""
    if n < 1 or not 0 <= successes <= n:
        raise ValueError(f"successes must be between 0 and n >= 1, not {successes} of {n}")
    if not 0 < level < 1:
        raise ValueError(f"level must be strictly between 0 and 1, not {level}")
    z = NormalDist().inv_cdf(float(1 - (1 - level) / 2))
    share = successes / n
    denominator = 1 + z * z / n
    centre = (share + z * z / (2 * n)) / denominator
    half = z * math.sqrt(share * (1 - share) / n + z * z / (4 * n * n)) / denominator
    # The ends that are exact are returned exact: no decision blocked is a lower end of 0, not of 1e-17.
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return low, high
