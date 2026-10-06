"""The paired bootstrap against cases whose answer is known without running it.

Three kinds of evidence, because each catches a different way of being wrong:
- degenerate cases, where the answer is exact (no variation between cases → an interval of zero width);
- an ANALYTIC case, where theory gives the interval (a proportion over n cases) and the bootstrap must land on
  it. Getting the centre right and the width wrong is the classic silent bug;
- mechanics: same seed same answer, case order irrelevant, and the two interval ends counted from ranks.
"""

import math
from fractions import Fraction as F

import pytest

from evalgate.stats.paired_bootstrap import Bootstrap, CaseMismatch, paired_bootstrap

LEVEL = F(95, 100)


def cases(values: list[float]) -> dict[str, float]:
    return {f"c{i:04d}": value for i, value in enumerate(values)}


def test_two_identical_runs_differ_by_exactly_nothing() -> None:
    run = cases([0.0, 1.0, 1.0, 0.5, 0.25] * 20)

    result = paired_bootstrap(run, run, replicates=2000, seed=42, level=LEVEL)

    assert result == Bootstrap(n=100, replicates=2000, delta=0.0, ci_low=0.0, ci_high=0.0, not_worse=F(1))


def test_the_same_drop_in_every_case_is_an_interval_of_zero_width() -> None:
    """Every case loses exactly 0.25. No resample can see anything else, whatever the cases look like."""
    base = cases([1.0, 0.5, 0.75, 0.25] * 25)
    head = {case: value - 0.25 for case, value in base.items()}

    result = paired_bootstrap(base, head, replicates=2000, seed=42, level=LEVEL)

    assert (result.delta, result.ci_low, result.ci_high) == (-0.25, -0.25, -0.25)
    assert result.not_worse == F(0)


def test_a_drop_in_a_proportion_lands_on_the_interval_theory_gives() -> None:
    """400 cases, all right in base; head gets 60 of them wrong. The paired differences are 60 times -1 and
    340 times 0: mean -0.15, standard deviation sqrt(0.15 x 0.85) = 0.3571, standard error 0.3571 / 20 =
    0.01785, so the 95 % interval is -0.15 ± 1.96 x 0.01785 = [-0.1850, -0.1150]."""
    base = cases([1.0] * 400)
    head = cases([0.0] * 60 + [1.0] * 340)
    half_width = 1.96 * math.sqrt(0.15 * 0.85) / math.sqrt(400)

    result = paired_bootstrap(base, head, replicates=10_000, seed=42, level=LEVEL)

    assert result.delta == pytest.approx(-0.15)
    assert result.ci_low == pytest.approx(-0.15 - half_width, abs=0.1 * half_width)
    assert result.ci_high == pytest.approx(-0.15 + half_width, abs=0.1 * half_width)
    assert result.not_worse == F(0)


def test_a_wider_confidence_level_gives_a_wider_interval() -> None:
    base = cases([1.0] * 200)
    head = cases([0.0] * 30 + [1.0] * 170)

    narrow = paired_bootstrap(base, head, replicates=4000, seed=7, level=F(80, 100))
    wide = paired_bootstrap(base, head, replicates=4000, seed=7, level=F(99, 100))

    assert wide.ci_low < narrow.ci_low < narrow.ci_high < wide.ci_high


def test_the_interval_ends_are_ranks_of_the_replicates_and_agree_with_the_count() -> None:
    """ci_high < 0 must mean exactly "at most alpha of the replicates were not worse": the report shows the
    interval, the gate decides on the count, and they may never disagree."""
    base = cases([1.0] * 120)
    head = cases([0.0] * 9 + [1.0] * 111)
    alpha = (1 - LEVEL) / 2

    result = paired_bootstrap(base, head, replicates=1000, seed=3, level=LEVEL)

    assert (result.ci_high < 0) == (result.not_worse <= alpha)


def test_the_same_seed_gives_the_same_answer_and_another_seed_another() -> None:
    base = cases([1.0, 0.0, 1.0, 1.0] * 50)
    head = cases([1.0, 0.0, 0.0, 1.0] * 50)

    first = paired_bootstrap(base, head, replicates=2000, seed=42, level=LEVEL)

    assert paired_bootstrap(base, head, replicates=2000, seed=42, level=LEVEL) == first
    assert paired_bootstrap(base, head, replicates=2000, seed=43, level=LEVEL) != first


def test_the_order_the_cases_are_listed_in_changes_nothing() -> None:
    base = cases([1.0, 0.0, 1.0, 1.0] * 50)
    head = cases([1.0, 0.0, 0.0, 1.0] * 50)
    backwards = dict(reversed(list(head.items())))

    assert paired_bootstrap(base, backwards, replicates=2000, seed=42, level=LEVEL) == paired_bootstrap(
        base, head, replicates=2000, seed=42, level=LEVEL
    )


def test_runs_over_different_cases_are_not_compared_and_the_cases_are_named() -> None:
    base = cases([1.0, 1.0, 1.0])
    head = {"c0000": 1.0, "c0001": 1.0, "nuevo": 0.0}

    with pytest.raises(CaseMismatch, match=r"c0002.*nuevo|nuevo.*c0002"):
        paired_bootstrap(base, head, replicates=1000, seed=42, level=LEVEL)


@pytest.mark.parametrize(
    ("replicates", "level", "reason"),
    [(0, LEVEL, "replicates"), (1000, F(0), "level"), (1000, F(1), "level"), (1000, F(3, 2), "level")],
)
def test_parameters_that_make_no_interval_are_refused(replicates: int, level: F, reason: str) -> None:
    run = cases([1.0, 0.0])

    with pytest.raises(ValueError, match=reason):
        paired_bootstrap(run, run, replicates=replicates, seed=1, level=level)


def test_no_cases_no_comparison() -> None:
    with pytest.raises(ValueError, match="no cases"):
        paired_bootstrap({}, {}, replicates=1000, seed=1, level=LEVEL)
