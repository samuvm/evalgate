"""`compare`: two runs in, a decision and the report's `comparison` block out.

The runs are small and built so the answer is known before running: every case drops by the same amount (an
interval of zero width, certainly worse), or nothing changes at all.
"""

import json
from fractions import Fraction as F
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from evalgate.gate.compare import (
    GateConfig,
    MetricRule,
    MissingMetric,
    compare,
    comparison_block,
    metric_seed,
)
from evalgate.gate.decision import ALLOW, BLOCK, Policy
from evalgate.stats.paired_bootstrap import CaseMismatch

ROOT = Path(__file__).resolve().parents[3]
POLICY = Policy(level=F(95, 100), correction="holm", correction_above=3)
CASES = [f"c{i:03d}" for i in range(60)]


def config(*rules: MetricRule, replicates: int = 1000) -> GateConfig:
    return GateConfig(replicates=replicates, seed=42, policy=POLICY, rules=rules)


def flat(value: float) -> dict[str, float]:
    return dict.fromkeys(CASES, value)


def varied(shift: float = 0.0) -> dict[str, float]:
    return {case: (i % 4) / 4 + shift for i, case in enumerate(CASES)}


def test_an_unchanged_run_passes_with_a_delta_of_exactly_zero() -> None:
    run = {"faithfulness": varied()}

    result = compare(run, run, config(MetricRule("faithfulness", blocking=True)))

    assert result.outcome == ALLOW
    (metric,) = result.metrics
    assert (metric.delta, metric.ci_low, metric.ci_high) == (0.0, 0.0, 0.0)
    assert metric.base_value == metric.head_value == pytest.approx(0.375)


def test_a_drop_in_every_case_blocks_and_reports_the_drop_in_the_metrics_own_sign() -> None:
    base, head = {"faithfulness": varied()}, {"faithfulness": varied(-0.125)}

    result = compare(base, head, config(MetricRule("faithfulness", blocking=True)))

    assert result.outcome == BLOCK
    (metric,) = result.metrics
    assert (metric.delta, metric.ci_low, metric.ci_high) == (-0.125, -0.125, -0.125)
    assert metric.verdict.blocking


def test_for_a_metric_where_lower_is_better_a_rise_is_what_blocks() -> None:
    """Hallucination rate goes UP by 0.125 in every case. The delta is reported as +0.125, as measured, and
    it blocks; the same rise in a higher-is-better metric would be an improvement."""
    base, head = {"alucinacion": varied()}, {"alucinacion": varied(0.125)}

    worse = compare(base, head, config(MetricRule("alucinacion", blocking=True, higher_is_better=False)))
    better = compare(base, head, config(MetricRule("alucinacion", blocking=True, higher_is_better=True)))

    assert (worse.outcome, worse.metrics[0].delta) == (BLOCK, 0.125)
    assert (worse.metrics[0].ci_low, worse.metrics[0].ci_high) == (0.125, 0.125)
    assert better.outcome == ALLOW


def test_the_absolute_threshold_is_a_floor_or_a_ceiling_depending_on_the_direction() -> None:
    floor = MetricRule("faithfulness", blocking=True, absolute=0.9)
    ceiling = MetricRule("alucinacion", blocking=True, higher_is_better=False, absolute=0.05)
    base = {"faithfulness": flat(0.95), "alucinacion": flat(0.0)}
    head = {"faithfulness": flat(0.85), "alucinacion": flat(0.10)}

    result = compare(base, head, config(floor, ceiling))

    assert [m.breaches_absolute for m in result.metrics] == [True, True]
    assert [m.verdict.fell_below_absolute for m in result.metrics] == [True, True]


def test_exactly_on_the_threshold_is_not_a_breach() -> None:
    rule = MetricRule("faithfulness", blocking=True, absolute=0.5)

    result = compare({"faithfulness": flat(0.5)}, {"faithfulness": flat(0.5)}, config(rule))

    assert result.metrics[0].breaches_absolute is False


def test_a_metric_the_gate_must_judge_and_a_run_does_not_have_is_an_error() -> None:
    rule = MetricRule("faithfulness", blocking=True)

    with pytest.raises(MissingMetric, match="faithfulness"):
        compare({"otra": flat(1.0)}, {"faithfulness": flat(1.0)}, config(rule))
    with pytest.raises(MissingMetric, match="faithfulness"):
        compare({"faithfulness": flat(1.0)}, {"otra": flat(1.0)}, config(rule))


def test_runs_over_different_cases_are_refused_whatever_the_metric_says() -> None:
    base = {"faithfulness": flat(1.0)}
    head = {"faithfulness": {**flat(1.0), "caso-nuevo": 0.0}}

    with pytest.raises(CaseMismatch, match="caso-nuevo"):
        compare(base, head, config(MetricRule("faithfulness", blocking=True)))


def test_a_gate_with_nothing_to_judge_is_a_misconfiguration_not_a_pass() -> None:
    with pytest.raises(ValueError, match="no rules"):
        compare({"m": flat(1.0)}, {"m": flat(1.0)}, config())


def test_metrics_nobody_asked_about_are_not_judged() -> None:
    base = {"faithfulness": varied(), "ruido": varied()}
    head = {"faithfulness": varied(), "ruido": varied(-0.5)}

    result = compare(base, head, config(MetricRule("faithfulness", blocking=True)))

    assert (result.outcome, [m.rule.metric for m in result.metrics]) == (ALLOW, ["faithfulness"])


def test_each_metric_is_resampled_with_its_own_seed_derived_from_the_one_configured() -> None:
    """So adding or removing a metric never changes the interval of another: the report of a metric depends
    on that metric and on the configured seed, and on nothing else."""
    assert metric_seed(42, "faithfulness") == metric_seed(42, "faithfulness")
    assert metric_seed(42, "faithfulness") != metric_seed(42, "relevancia")
    assert metric_seed(42, "faithfulness") != metric_seed(43, "faithfulness")

    noisy_base = {"a": varied(), "b": varied()}
    noisy_head = {"a": {c: 1.0 - v for c, v in varied().items()}, "b": varied(-0.125)}
    alone = compare(noisy_base, noisy_head, config(MetricRule("a", blocking=False)))
    together = compare(
        noisy_base, noisy_head, config(MetricRule("b", blocking=True), MetricRule("a", blocking=False))
    )

    assert alone.metrics[0] == together.metrics[1]


def test_more_than_three_blocking_metrics_and_the_report_says_holm_literally() -> None:
    """R8: with more than three blocking metrics watched, every report writes "holm". And it validates
    against the shared eval-report contract."""
    names = ["a", "b", "c", "d"]
    base = {name: varied() for name in names}
    head = {**base, "a": varied(-0.125)}
    result = compare(base, head, config(*(MetricRule(name, blocking=True) for name in names)))

    block = comparison_block(result, base_run_id="run-base-1")

    assert block["method"] == {
        "kind": "bootstrap",
        "paired": True,
        "replicates": 1000,
        "multiple_comparison_correction": "holm",
    }
    assert block["decision"] == "block"
    assert block["base_run_id"] == "run-base-1"
    assert block["deltas"][0] == {
        "id": "a",
        "delta": -0.125,
        "ci95": [-0.125, -0.125],
        "below_absolute_threshold": False,
        "blocking": True,
    }
    schema = json.loads((ROOT / "docs" / "CONTRACTS" / "eval-report.schema.json").read_text("utf-8"))
    comparison_schema = {**schema["properties"]["comparison"], "$defs": schema.get("$defs", {})}
    assert list(Draft202012Validator(comparison_schema).iter_errors(block)) == []


def test_with_three_blocking_metrics_or_fewer_the_report_says_no_correction_was_applied() -> None:
    result = compare({"a": varied()}, {"a": varied()}, config(MetricRule("a", blocking=True)))

    block = comparison_block(result, base_run_id="b")

    assert block["method"]["multiple_comparison_correction"] is None
    assert block["decision"] == "pass"
