"""The empirical percentile G-GATE-MDE reads from the matrix: a value that was observed, never invented."""

from fractions import Fraction as F

import pytest

from evalgate.stats.percentile import empirical_percentile


def test_the_95th_of_one_to_twenty_is_nineteen() -> None:
    """Nearest rank: ceil(0.95 · 20) = 19, the 19th smallest value."""
    assert empirical_percentile([float(v) for v in range(1, 21)], F(95)) == 19.0


def test_the_rank_is_rounded_up() -> None:
    """ceil(0.95 · 49) = ceil(46.55) = 47: with 49 deltas, two are left above."""
    values = [float(v) for v in range(49)]

    assert empirical_percentile(values, F(95)) == 46.0


def test_the_order_given_does_not_matter() -> None:
    assert empirical_percentile([5.0, 1.0, 4.0, 2.0, 3.0], F(50)) == 3.0


def test_the_hundredth_is_the_maximum_and_a_tiny_one_the_minimum() -> None:
    values = [0.25, -1.5, 3.0, 0.0]

    assert empirical_percentile(values, F(100)) == 3.0
    assert empirical_percentile(values, F(1, 1000)) == -1.5


def test_a_single_value_is_every_percentile() -> None:
    assert empirical_percentile([0.5], F(95)) == 0.5


def test_ties_are_values_like_any_other() -> None:
    assert empirical_percentile([0.0] * 18 + [1.0, 2.0], F(90)) == 0.0
    assert empirical_percentile([0.0] * 18 + [1.0, 2.0], F(95)) == 1.0


def test_nothing_to_read_is_refused() -> None:
    with pytest.raises(ValueError, match="no values"):
        empirical_percentile([], F(95))


@pytest.mark.parametrize("percent", [F(0), F(-5), F(101)])
def test_a_percent_outside_its_range_is_refused(percent: F) -> None:
    with pytest.raises(ValueError, match="percent"):
        empirical_percentile([1.0, 2.0], percent)
