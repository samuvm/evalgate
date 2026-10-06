"""Holm-Bonferroni against cases worked out by hand, and against the textbook step-down procedure.

Adjusted p-values are used instead of adjusted thresholds because they compose: "block if adjusted p <= alpha"
is one rule whatever the number of metrics, and the report can show the number that decided.
"""

from fractions import Fraction as F

import pytest

from evalgate.stats.holm import holm_adjust


def test_a_single_hypothesis_is_not_adjusted() -> None:
    assert holm_adjust([F(1, 50)]) == [F(1, 50)]


def test_no_hypotheses_no_adjustment() -> None:
    assert holm_adjust([]) == []


def test_the_worked_example_step_by_step() -> None:
    """m = 4, sorted p: 0.01, 0.02, 0.03, 0.04.
    Step-down multipliers 4, 3, 2, 1 → 0.04, 0.06, 0.06, 0.04; made monotone → 0.04, 0.06, 0.06, 0.06."""
    adjusted = holm_adjust([F(1, 100), F(2, 100), F(3, 100), F(4, 100)])

    assert adjusted == [F(4, 100), F(6, 100), F(6, 100), F(6, 100)]


def test_the_answer_comes_back_in_the_order_of_the_question() -> None:
    """Same four p-values, shuffled: each metric keeps ITS adjusted value, not the one of its rank."""
    adjusted = holm_adjust([F(4, 100), F(1, 100), F(3, 100), F(2, 100)])

    assert adjusted == [F(6, 100), F(4, 100), F(6, 100), F(6, 100)]


def test_an_adjusted_p_value_never_exceeds_one() -> None:
    assert holm_adjust([F(1, 2), F(3, 4), F(9, 10)]) == [F(1), F(1), F(1)]


def test_ties_get_the_same_adjusted_value() -> None:
    assert holm_adjust([F(1, 100), F(1, 100), F(1, 2)]) == [F(3, 100), F(3, 100), F(1, 2)]


def test_holm_rejects_what_bonferroni_rejects_and_more() -> None:
    """The reason the contract prefers it: at alpha = 0.05 and m = 4, Bonferroni (p <= 0.0125) rejects only
    the first; Holm also rejects the second (0.015 <= 0.05 / 3) and then stops at the third."""
    p_values = [F(10, 1000), F(15, 1000), F(40, 1000), F(45, 1000)]
    alpha = F(5, 100)

    holm = [adjusted <= alpha for adjusted in holm_adjust(p_values)]
    bonferroni = [p * len(p_values) <= alpha for p in p_values]

    assert bonferroni == [True, False, False, False]
    assert holm == [True, True, False, False]


@pytest.mark.parametrize("bad", [[F(-1, 10)], [F(11, 10)], [F(1, 2), F(3, 2)]])
def test_a_p_value_outside_zero_one_is_corrupt_input(bad: list[F]) -> None:
    with pytest.raises(ValueError, match="p-value"):
        holm_adjust(bad)
