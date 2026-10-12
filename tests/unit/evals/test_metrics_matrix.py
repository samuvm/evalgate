"""False positives, minimum detectable effect and power, on matrices small enough to work out by hand."""

from fractions import Fraction as F

import pytest

from evalgate.evals.metrics.matrix import (
    decisions,
    degradation_size,
    false_positive_block,
    mde_block,
    power_block,
)
from evalgate.gate.compare import GateConfig, MetricRule
from evalgate.gate.decision import Policy

CASES = [f"c{i:02d}" for i in range(20)]
RULES = (
    MetricRule("acierto", blocking=True),
    MetricRule("alucina", blocking=True, higher_is_better=False),
    MetricRule("extra", blocking=False),
)
CONFIG = GateConfig(replicates=400, seed=42, policy=Policy(F(95, 100), "holm", 3), rules=RULES)


def run(right: int, hallucinated: int = 0, extra: int = 20) -> dict[str, dict[str, float]]:
    """A run over 20 cases: the first `right` are right, the first `hallucinated` hallucinate."""
    return {
        "acierto": {case: float(i < right) for i, case in enumerate(CASES)},
        "alucina": {case: float(i < hallucinated) for i, case in enumerate(CASES)},
        "extra": {case: float(i < extra) for i, case in enumerate(CASES)},
    }


def test_identical_runs_are_never_blocked() -> None:
    h0 = {f"base-{i:02d}": run(16) for i in range(6)}

    block = false_positive_block(h0, "base-00", CONFIG)

    assert (block["point"], block["blocked"], block["n"]) == (0.0, 0, 5)
    assert block["wilson_95"][0] == 0.0
    assert 0.0 < block["wilson_95"][1] < 1.0
    assert block["blocked_runs"] == []
    assert block["baseline"] == "base-00"


def test_a_block_under_h0_is_counted_and_says_which_metric_did_it() -> None:
    """Four candidates, one of them 10 cases worse: 1 of 4 blocked, by `acierto`."""
    h0 = {"base-00": run(16), "base-01": run(16), "base-02": run(6), "base-03": run(16), "base-04": run(17)}

    block = false_positive_block(h0, "base-00", CONFIG)

    assert (block["point"], block["blocked"], block["n"]) == (0.25, 1, 4)
    assert block["blocked_runs"] == ["base-02"]
    assert block["blocked_by_metric"] == {"acierto": 1}


def test_a_metric_that_only_informs_never_makes_a_false_positive() -> None:
    h0 = {"base-00": run(16), "base-01": run(16, extra=2)}

    assert false_positive_block(h0, "base-00", CONFIG)["blocked"] == 0


def test_the_baseline_has_to_be_one_of_the_runs() -> None:
    with pytest.raises(ValueError, match="baseline"):
        false_positive_block({"base-01": run(16)}, "base-00", CONFIG)


def test_one_run_alone_gives_no_decisions() -> None:
    with pytest.raises(ValueError, match="no decisions"):
        false_positive_block({"base-00": run(16)}, "base-00", CONFIG)


def test_decisions_name_every_candidate() -> None:
    judged = decisions(run(16), {"b": run(16), "a": run(4)}, CONFIG)

    assert list(judged) == ["a", "b"]
    assert judged["a"] == {"outcome": "block", "blocked_by": ["acierto"]}
    assert judged["b"] == {"outcome": "pass", "blocked_by": []}


def test_the_mde_is_the_percentile_of_the_drop_between_two_h0_runs() -> None:
    """Three runs with 16, 17 and 18 right of 20: means 0.80, 0.85, 0.90. The six ordered pairs drop by
    -10, -5, -5, +5, +5, +10 points. Percentile 95 -> rank ceil(5.7) = 6 -> 10; percentile 50 -> rank 3 -> -5."""
    h0 = {"a": run(16), "b": run(17), "c": run(18)}

    block = mde_block(h0, RULES, F(95))

    assert block["per_metric"]["acierto"]["point"] == pytest.approx(10.0)
    assert block["per_metric"]["acierto"]["max"] == pytest.approx(10.0)
    assert block["per_metric"]["acierto"]["h0_mean"] == pytest.approx(0.85)
    assert block["per_metric"]["alucina"]["point"] == 0.0
    assert (block["point"], block["limiting_metric"]) == (pytest.approx(10.0), "acierto")
    assert (block["n_runs"], block["n_pairs"], block["percentile"]) == (3, 6, 95.0)
    assert "extra" not in block["per_metric"], "a metric that cannot block has no detectable effect to publish"
    assert mde_block(h0, RULES, F(50))["per_metric"]["acierto"]["point"] == pytest.approx(-5.0)


def test_the_mde_of_a_rate_that_should_stay_low_counts_its_rise() -> None:
    h0 = {"a": run(16, hallucinated=0), "b": run(16, hallucinated=3)}

    block = mde_block(h0, RULES, F(95))

    assert (block["point"], block["limiting_metric"]) == (pytest.approx(15.0), "alucina")


def test_the_mde_needs_two_runs_and_a_blocking_metric() -> None:
    with pytest.raises(ValueError, match="two H0 runs"):
        mde_block({"a": run(16)}, RULES, F(95))
    with pytest.raises(ValueError, match="no blocking metric"):
        mde_block({"a": run(16), "b": run(15)}, (MetricRule("extra", blocking=False),), F(95))


def test_the_size_of_a_degradation_is_the_metric_it_hurts_most() -> None:
    """H0 averages 17/20 right and 0 hallucinations; degraded averages 11/20 and 2/20: 30 and 10 points."""
    h0 = {"a": run(16), "b": run(18)}
    degraded = {"x": run(10, hallucinated=2), "y": run(12, hallucinated=2)}

    size = degradation_size(h0, degraded, RULES)

    assert size["drop_pp_per_metric"] == {"acierto": pytest.approx(30.0), "alucina": pytest.approx(10.0)}
    assert (size["size_pp"], size["size_metric"]) == (pytest.approx(30.0), "acierto")


def test_a_size_needs_runs_on_both_sides() -> None:
    with pytest.raises(ValueError, match="both sides"):
        degradation_size({"a": run(16)}, {}, RULES)


def test_power_is_blocks_over_runs_and_the_minimum_is_over_the_big_degradations() -> None:
    """`grande` loses 10 cases in every run: always blocked. `media` is blocked in one run of two. `nimia`
    loses one case: never blocked, and at 5 points it is under 1.5 x MDE (= 6), so it is not demanded."""
    h0 = {"base-00": run(16), "base-01": run(16)}
    degradations = {
        "grande": {"g0": run(6), "g1": run(6)},
        "media": {"m0": run(6), "m1": run(16)},
        "nimia": {"n0": run(15), "n1": run(15)},
    }

    block = power_block(h0, "base-00", degradations, CONFIG, mde_pp=4.0, min_size_over_mde=F(3, 2))

    per = block["per_degradation"]
    assert (per["grande"]["power"], per["grande"]["blocked"], per["grande"]["n"]) == (1.0, 2, 2)
    assert per["grande"]["blocked_by_metric"] == {"acierto": 2}
    assert per["grande"]["size_pp"] == pytest.approx(50.0)
    assert per["media"]["power"] == 0.5
    assert (per["nimia"]["power"], per["nimia"]["big_enough"]) == (0.0, False)
    assert block["required_size_pp"] == pytest.approx(6.0)
    assert block["below_required_size"] == ["nimia"]
    assert block["min_over_degradations"] == 0.5
    assert block["min_over_all"] == 0.0
    assert (block["mde_pp"], block["min_size_over_mde"], block["baseline"]) == (4.0, 1.5, "base-00")


def test_a_degradation_exactly_at_the_required_size_is_demanded() -> None:
    h0 = {"base-00": run(16)}

    block = power_block(h0, "base-00", {"justa": {"j0": run(13)}}, CONFIG, mde_pp=10.0, min_size_over_mde=F(3, 2))

    assert block["per_degradation"]["justa"]["size_pp"] == pytest.approx(15.0)
    assert block["below_required_size"] == []


def test_with_no_degradation_big_enough_there_is_no_power_to_publish() -> None:
    h0 = {"base-00": run(16)}

    block = power_block(h0, "base-00", {"nimia": {"n0": run(15)}}, CONFIG, mde_pp=20.0, min_size_over_mde=F(3, 2))

    assert block["min_over_degradations"] is None
    assert block["min_over_all"] == 0.0


def test_power_refuses_a_missing_baseline_and_an_empty_experiment() -> None:
    with pytest.raises(ValueError, match="baseline"):
        power_block({"base-01": run(16)}, "base-00", {"d": {"x": run(1)}}, CONFIG, mde_pp=1.0, min_size_over_mde=F(1))
    with pytest.raises(ValueError, match="no degradations"):
        power_block({"base-00": run(16)}, "base-00", {}, CONFIG, mde_pp=1.0, min_size_over_mde=F(1))
