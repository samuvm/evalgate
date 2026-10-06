"""The gate's decision, case by case. This is the module where a bug blocks good changes or lets bad ones
through, so every rule of docs/CONTRACTS/retrieval-metrics.md §4 has its test and so does every boundary.

The evidence is built by hand (`boot`): the decision must not depend on how a bootstrap came out, only on
what it says. `not_worse` is the share of replicates in which the change was NOT worse; with a 95 % interval
the change is significantly worse when that share is <= 2.5 %.
"""

from fractions import Fraction as F

import pytest

from evalgate.gate.decision import ALLOW, BLOCK, Evidence, Policy, decide
from evalgate.stats.paired_bootstrap import Bootstrap

POLICY = Policy(level=F(95, 100), correction="holm", correction_above=3)


def boot(not_worse: F, delta: float = -0.05) -> Bootstrap:
    return Bootstrap(
        n=200, replicates=10_000, delta=delta, ci_low=delta - 0.03, ci_high=delta + 0.03, not_worse=not_worse
    )


def ev(
    metric: str, not_worse: F, *, blocking: bool = True, breaches: bool = False, delta: float = -0.05
) -> Evidence:
    return Evidence(metric, blocking, boot(not_worse, delta), breaches)


CLEARLY_WORSE, NOISE = F(1, 1000), F(40, 100)


def test_a_change_that_is_within_the_noise_passes() -> None:
    decision = decide([ev("faithfulness", NOISE)], POLICY)

    assert decision.outcome == ALLOW
    assert [(v.blocking, v.significant) for v in decision.verdicts] == [(False, False)]


def test_a_change_whose_interval_is_entirely_worse_blocks() -> None:
    decision = decide([ev("faithfulness", CLEARLY_WORSE)], POLICY)

    assert decision.outcome == BLOCK
    assert [(v.metric, v.blocking, v.significant) for v in decision.verdicts] == [
        ("faithfulness", True, True)
    ]


@pytest.mark.parametrize(
    ("not_worse", "outcome"),
    [(F(250, 10_000), BLOCK), (F(251, 10_000), ALLOW)],
)
def test_the_boundary_is_exactly_alpha_and_it_is_inclusive(not_worse: F, outcome: str) -> None:
    """95 % → alpha = 2.5 %. With 10,000 replicates, 250 not-worse is ci_high < 0 and 251 is not: the same
    boundary the bootstrap's ranks draw, to the replicate."""
    assert decide([ev("m", not_worse)], POLICY).outcome == outcome


def test_one_bad_metric_among_good_ones_is_enough_to_block() -> None:
    decision = decide([ev("a", NOISE), ev("b", CLEARLY_WORSE), ev("c", NOISE)], POLICY)

    assert decision.outcome == BLOCK
    assert [v.metric for v in decision.verdicts if v.blocking] == ["b"]


def test_a_metric_that_is_only_watched_never_blocks_however_bad() -> None:
    decision = decide([ev("diagnostico", CLEARLY_WORSE, blocking=False, breaches=True)], POLICY)

    assert decision.outcome == ALLOW
    (verdict,) = decision.verdicts
    assert (verdict.blocking, verdict.significant, verdict.fell_below_absolute) == (False, True, True)


def test_up_to_three_blocking_metrics_no_correction_is_applied_or_claimed() -> None:
    """Contract: the correction is for MORE than three. With three, p = 2 % blocks on its own."""
    decision = decide([ev("a", F(2, 100)), ev("b", NOISE), ev("c", NOISE)], POLICY)

    assert (decision.outcome, decision.correction) == (BLOCK, None)
    assert decision.verdicts[0].p_value == F(2, 100)


def test_with_four_blocking_metrics_holm_is_applied_and_named() -> None:
    """The same p = 2 % that blocked among three does not among four: 4 x 2 % = 8 % > 2.5 %. That is the
    family-wise error being controlled, and the report says which correction did it."""
    decision = decide([ev("a", F(2, 100)), ev("b", NOISE), ev("c", NOISE), ev("d", NOISE)], POLICY)

    assert (decision.outcome, decision.correction) == (ALLOW, "holm")
    assert decision.verdicts[0].p_value == F(8, 100)


def test_holm_still_blocks_what_is_clearly_worse_among_four() -> None:
    decision = decide([ev("a", CLEARLY_WORSE), ev("b", NOISE), ev("c", NOISE), ev("d", NOISE)], POLICY)

    assert decision.outcome == BLOCK
    assert decision.verdicts[0].p_value == F(4, 1000)


def test_watched_only_metrics_do_not_count_towards_the_family() -> None:
    """Three blocking and five informative ones is a family of three: no correction. Otherwise adding a
    diagnostic metric to a panel would make the gate deafer."""
    watched = [ev(f"info{i}", NOISE, blocking=False) for i in range(5)]
    decision = decide([ev("a", F(2, 100)), ev("b", NOISE), ev("c", NOISE), *watched], POLICY)

    assert (decision.outcome, decision.correction) == (BLOCK, None)


def test_falling_below_the_absolute_threshold_blocks_even_inside_the_noise() -> None:
    decision = decide([ev("faithfulness", NOISE, breaches=True, delta=-0.01)], POLICY)

    assert decision.outcome == BLOCK
    (verdict,) = decision.verdicts
    assert (verdict.significant, verdict.fell_below_absolute, verdict.blocking) == (False, True, True)


@pytest.mark.parametrize("delta", [0.0, 0.02])
def test_a_metric_already_below_its_threshold_that_did_not_get_worse_does_not_block(delta: float) -> None:
    """The gate judges the CHANGE. Below the floor and flat, or below and improving, is not a regression this
    change caused, and blocking it would block the very fix. It also makes compare(a, a) never block (R9)."""
    decision = decide(
        [ev("faithfulness", F(1) if delta == 0 else F(99, 100), breaches=True, delta=delta)], POLICY
    )

    assert decision.outcome == ALLOW
    assert decision.verdicts[0].fell_below_absolute is False


def test_verdicts_come_back_in_the_order_the_metrics_were_given() -> None:
    decision = decide([ev("z", NOISE), ev("a", CLEARLY_WORSE), ev("m", NOISE, blocking=False)], POLICY)

    assert [v.metric for v in decision.verdicts] == ["z", "a", "m"]


def test_nothing_to_judge_passes_and_says_so() -> None:
    assert decide([], POLICY) == decide([], POLICY)
    assert decide([], POLICY).outcome == ALLOW


def test_a_big_family_without_a_correction_configured_is_refused_not_waved_through() -> None:
    """Contract: mandatory above three. A config that forgot it must not silently run uncorrected."""
    four = [ev(name, NOISE) for name in "abcd"]

    with pytest.raises(ValueError, match="correction"):
        decide(four, Policy(level=F(95, 100), correction=None, correction_above=3))


def test_a_correction_the_gate_does_not_implement_is_refused() -> None:
    four = [ev(name, NOISE) for name in "abcd"]

    with pytest.raises(ValueError, match="benjamini-hochberg"):
        decide(four, Policy(level=F(95, 100), correction="benjamini-hochberg", correction_above=3))


def test_the_same_metric_twice_is_corrupt_input() -> None:
    with pytest.raises(ValueError, match="faithfulness"):
        decide([ev("faithfulness", NOISE), ev("faithfulness", NOISE)], POLICY)


def test_the_confidence_level_moves_the_boundary() -> None:
    """Nothing about 95 % is written in the decision: at 99 % the same evidence stops being enough."""
    evidence = [ev("m", F(2, 100))]

    assert decide(evidence, POLICY).outcome == BLOCK
    assert decide(evidence, Policy(level=F(99, 100), correction="holm", correction_above=3)).outcome == ALLOW
