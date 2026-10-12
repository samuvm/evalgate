"""Wilson's interval for a proportion, against cases worked out by hand (G-GATE-FP publishes it)."""

from fractions import Fraction as F

import pytest

from evalgate.stats.wilson import wilson_interval

LEVEL = F(95, 100)
Z2 = 1.959963984540054**2  # the 97.5 % point of the normal, squared


def test_no_blocks_in_49_decisions() -> None:
    """0 of n: the lower end is 0 and the upper end is z² / (n + z²). With n = 49, about 7.3 %."""
    low, high = wilson_interval(0, 49, LEVEL)

    assert low == 0.0
    assert high == pytest.approx(Z2 / (49 + Z2))
    assert high == pytest.approx(0.0727, abs=5e-5)


def test_one_block_in_20_is_the_interval_goals_quotes() -> None:
    """GOALS.yaml G-GATE-FP: "con n=20 y 1 bloqueo el IC95 es ~[1 %, 24 %]"."""
    low, high = wilson_interval(1, 20, LEVEL)

    assert low == pytest.approx(0.0089, abs=5e-5)
    assert high == pytest.approx(0.2361, abs=5e-5)


def test_half_and_half_by_the_formula() -> None:
    """p = 1/2, n = 100: centre 1/2, half width z·sqrt(1/400 + z²/40000) / (1 + z²/100)."""
    low, high = wilson_interval(50, 100, LEVEL)
    half = (Z2**0.5) * (1 / 400 + Z2 / 40000) ** 0.5 / (1 + Z2 / 100)

    assert low == pytest.approx(0.5 - half)
    assert high == pytest.approx(0.5 + half)
    assert low + high == pytest.approx(1.0)


def test_every_decision_blocked_mirrors_none_blocked() -> None:
    low, high = wilson_interval(49, 49, LEVEL)

    assert high == 1.0
    assert low == pytest.approx(1 - Z2 / (49 + Z2))


def test_a_higher_level_is_a_wider_interval() -> None:
    narrow, wide = wilson_interval(3, 49, F(90, 100)), wilson_interval(3, 49, F(99, 100))

    assert wide[0] < narrow[0] < narrow[1] < wide[1]


@pytest.mark.parametrize(("successes", "n"), [(0, 0), (-1, 10), (11, 10), (1, -3)])
def test_counts_that_are_not_a_proportion_are_refused(successes: int, n: int) -> None:
    with pytest.raises(ValueError, match="successes"):
        wilson_interval(successes, n, LEVEL)


@pytest.mark.parametrize("level", [F(0), F(1), F(3, 2)])
def test_a_level_that_is_not_a_probability_is_refused(level: F) -> None:
    with pytest.raises(ValueError, match="level"):
        wilson_interval(1, 10, level)
