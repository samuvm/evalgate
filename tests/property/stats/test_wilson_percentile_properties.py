"""Properties of `wilson_interval` and `empirical_percentile` (RULES §4.2: every public
function of stats/)."""

import math
from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from evalgate.stats.percentile import empirical_percentile
from evalgate.stats.wilson import wilson_interval

LEVELS = st.sampled_from([Fraction(80, 100), Fraction(90, 100), Fraction(95, 100), Fraction(99, 100)])
COUNTS = st.integers(min_value=1, max_value=400).flatmap(
    lambda n: st.tuples(st.integers(min_value=0, max_value=n), st.just(n))
)
VALUES = st.lists(st.floats(min_value=-100, max_value=100, allow_nan=False), min_size=1, max_size=60)
PERCENTS = st.fractions(min_value=Fraction(1, 100), max_value=100)


@given(COUNTS, LEVELS)
def test_the_interval_is_inside_zero_one_and_holds_the_observed_share(
    counts: tuple[int, int], level: Fraction
) -> None:
    successes, n = counts
    low, high = wilson_interval(successes, n, level)

    assert 0.0 <= low <= high <= 1.0
    assert low - 1e-12 <= successes / n <= high + 1e-12


@given(COUNTS, LEVELS)
def test_counting_the_failures_instead_mirrors_the_interval(counts: tuple[int, int], level: Fraction) -> None:
    successes, n = counts
    low, high = wilson_interval(successes, n, level)
    mirrored_low, mirrored_high = wilson_interval(n - successes, n, level)

    assert math.isclose(low, 1 - mirrored_high, abs_tol=1e-12)
    assert math.isclose(high, 1 - mirrored_low, abs_tol=1e-12)


@given(COUNTS, LEVELS, st.integers(min_value=2, max_value=5))
def test_the_same_share_over_more_decisions_is_a_narrower_interval(
    counts: tuple[int, int], level: Fraction, times: int
) -> None:
    successes, n = counts
    low, high = wilson_interval(successes, n, level)
    more_low, more_high = wilson_interval(successes * times, n * times, level)

    assert more_high - more_low < high - low


@given(VALUES, PERCENTS)
def test_the_percentile_is_an_observed_value_with_its_share_at_or_below(
    values: list[float], percent: Fraction
) -> None:
    found = empirical_percentile(values, percent)

    assert found in values
    assert Fraction(sum(value <= found for value in values), len(values)) >= percent / 100
    # and it is the SMALLEST such value: below it, the share is short
    assert Fraction(sum(value < found for value in values), len(values)) < percent / 100


@given(VALUES, PERCENTS, PERCENTS)
def test_a_higher_percent_never_reads_a_lower_value(
    values: list[float], one: Fraction, other: Fraction
) -> None:
    low, high = sorted((one, other))

    assert empirical_percentile(values, low) <= empirical_percentile(values, high)


@given(VALUES, PERCENTS, st.randoms(use_true_random=False))
def test_shuffling_the_values_changes_nothing(values: list[float], percent: Fraction, rng) -> None:  # type: ignore[no-untyped-def]
    shuffled = list(values)
    rng.shuffle(shuffled)

    assert empirical_percentile(shuffled, percent) == empirical_percentile(values, percent)
