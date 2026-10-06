"""R9: the algebra of the gate. This is the file RULES names.

A gate is a function people will argue with, so it has to behave like one: comparing a run with itself never
blocks, swapping the runs mirrors every number, and what it says about one metric does not depend on which
other metrics happen to be listed.
"""

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from evalgate.gate.compare import GateConfig, MetricRule, compare, comparison_block, metric_seed
from evalgate.gate.decision import ALLOW, BLOCK, Policy

SCORES = st.floats(min_value=0, max_value=1, allow_nan=False, width=32)
METRICS = ["a", "b", "c", "d", "e"]
B = 200


@st.composite
def runs(draw: st.DrawFn) -> tuple[dict[str, dict[str, float]], dict[str, dict[str, float]]]:
    n = draw(st.integers(min_value=1, max_value=25))
    cases = [f"c{i}" for i in range(n)]
    names = METRICS[: draw(st.integers(min_value=1, max_value=len(METRICS)))]

    def run() -> dict[str, dict[str, float]]:
        return {
            m: dict(zip(cases, draw(st.lists(SCORES, min_size=n, max_size=n)), strict=True)) for m in names
        }

    return run(), run()


@st.composite
def configs(draw: st.DrawFn, names: list[str]) -> GateConfig:
    rules = tuple(
        MetricRule(
            name,
            blocking=draw(st.booleans()),
            higher_is_better=draw(st.booleans()),
            absolute=draw(st.none() | SCORES),
        )
        for name in names
    )
    policy = Policy(
        level=draw(st.sampled_from([Fraction(90, 100), Fraction(95, 100), Fraction(99, 100)])),
        correction="holm",
        correction_above=draw(st.integers(min_value=0, max_value=4)),
    )
    return GateConfig(
        replicates=B, seed=draw(st.integers(min_value=0, max_value=2**31)), policy=policy, rules=rules
    )


@given(st.data())
def test_a_run_compared_with_itself_never_blocks_whatever_the_thresholds(data: st.DataObject) -> None:
    """Including a run that is far below every absolute threshold: the gate judges the change."""
    run, _ = data.draw(runs())
    result = compare(run, run, data.draw(configs(list(run))))

    assert result.outcome == ALLOW
    assert all(m.delta == 0.0 and not m.verdict.blocking for m in result.metrics)


@given(st.data())
def test_swapping_the_runs_mirrors_every_delta_and_interval(data: st.DataObject) -> None:
    base, head = data.draw(runs())
    config = data.draw(configs(list(base)))
    forward, backward = compare(base, head, config), compare(head, base, config)

    for one, other in zip(forward.metrics, backward.metrics, strict=True):
        assert other.delta == -one.delta
        assert (other.ci_low, other.ci_high) == (-one.ci_high, -one.ci_low)
        assert (other.base_value, other.head_value) == (one.head_value, one.base_value)


@given(st.data())
def test_a_change_and_its_reverse_are_never_both_significantly_worse(data: st.DataObject) -> None:
    base, head = data.draw(runs())
    config = data.draw(configs(list(base)))
    forward, backward = compare(base, head, config), compare(head, base, config)

    for one, other in zip(forward.metrics, backward.metrics, strict=True):
        assert not (one.verdict.significant and other.verdict.significant)


@given(st.data())
def test_the_same_comparison_twice_is_the_same_comparison(data: st.DataObject) -> None:
    """G-DETERMINISM at the function: no clock, no global random state, no dict order."""
    base, head = data.draw(runs())
    config = data.draw(configs(list(base)))
    reordered = {m: dict(reversed(list(values.items()))) for m, values in reversed(list(head.items()))}

    assert compare(base, head, config) == compare(base, reordered, config)


@given(st.data())
def test_a_metric_that_only_informs_changes_nothing_about_the_others(data: st.DataObject) -> None:
    base, head = data.draw(runs())
    config = data.draw(configs(list(base)))
    extra_base = {**base, "extra": base[next(iter(base))]}
    extra_head = {**head, "extra": head[next(iter(head))]}
    watched = GateConfig(
        config.replicates, config.seed, config.policy, (*config.rules, MetricRule("extra", blocking=False))
    )

    with_extra = compare(extra_base, extra_head, watched)

    assert with_extra.outcome == compare(base, head, config).outcome
    assert with_extra.metrics[:-1] == compare(base, head, config).metrics


@given(st.data())
def test_the_report_block_says_what_the_comparison_decided(data: st.DataObject) -> None:
    base, head = data.draw(runs())
    result = compare(base, head, data.draw(configs(list(base))))
    block = comparison_block(result, "base")

    assert block["decision"] == result.outcome
    assert (block["decision"] == BLOCK) == any(delta["blocking"] for delta in block["deltas"])
    assert [delta["id"] for delta in block["deltas"]] == [m.rule.metric for m in result.metrics]
    assert block["method"]["multiple_comparison_correction"] == result.correction


@given(st.integers(min_value=0, max_value=2**31), st.sampled_from(METRICS), st.sampled_from(METRICS))
def test_metric_seeds_are_stable_and_distinct_per_metric(seed: int, one: str, other: str) -> None:
    assert metric_seed(seed, one) == metric_seed(seed, one)
    assert (metric_seed(seed, one) == metric_seed(seed, other)) == (one == other)
