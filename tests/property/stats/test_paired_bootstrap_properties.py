"""Properties of the paired bootstrap: the algebra the gate's own algebra (R9) is built on."""

from fractions import Fraction

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalgate.stats.paired_bootstrap import paired_bootstrap, tail

LEVEL = Fraction(95, 100)
B = 300
SCORES = st.floats(min_value=0, max_value=1, allow_nan=False, width=32)
SEEDS = st.integers(min_value=0, max_value=2**32)


@st.composite
def runs(draw: st.DrawFn) -> tuple[dict[str, float], dict[str, float]]:
    n = draw(st.integers(min_value=1, max_value=40))
    ids = [f"c{i}" for i in range(n)]
    return (
        dict(zip(ids, draw(st.lists(SCORES, min_size=n, max_size=n)), strict=True)),
        dict(zip(ids, draw(st.lists(SCORES, min_size=n, max_size=n)), strict=True)),
    )


@given(runs(), SEEDS)
def test_swapping_the_two_runs_mirrors_the_result_exactly(
    pair: tuple[dict[str, float], dict[str, float]], seed: int
) -> None:
    """Antisymmetry, to the last bit: delta flips sign and the interval is reflected. Not approximately."""
    base, head = pair
    forward = paired_bootstrap(base, head, replicates=B, seed=seed, level=LEVEL)
    backward = paired_bootstrap(head, base, replicates=B, seed=seed, level=LEVEL)

    assert backward.delta == -forward.delta
    assert (backward.ci_low, backward.ci_high) == (-forward.ci_high, -forward.ci_low)


@given(runs(), SEEDS)
def test_a_run_compared_with_itself_is_never_worse(
    pair: tuple[dict[str, float], dict[str, float]], seed: int
) -> None:
    run, _ = pair
    result = paired_bootstrap(run, run, replicates=B, seed=seed, level=LEVEL)

    assert (result.delta, result.ci_low, result.ci_high, result.not_worse) == (0.0, 0.0, 0.0, Fraction(1))


@given(runs(), SEEDS)
def test_the_interval_is_ordered_and_stays_within_the_per_case_differences(
    pair: tuple[dict[str, float], dict[str, float]], seed: int
) -> None:
    base, head = pair
    diffs = [head[case] - base[case] for case in base]
    result = paired_bootstrap(base, head, replicates=B, seed=seed, level=LEVEL)

    assert result.ci_low <= result.ci_high
    assert min(diffs) - 1e-12 <= result.ci_low
    assert result.ci_high <= max(diffs) + 1e-12
    assert 0 <= result.not_worse <= 1
    assert (result.n, result.replicates) == (len(base), B)


@given(runs(), SEEDS)
def test_the_interval_and_the_count_always_tell_the_same_story(
    pair: tuple[dict[str, float], dict[str, float]], seed: int
) -> None:
    base, head = pair
    result = paired_bootstrap(base, head, replicates=B, seed=seed, level=LEVEL)

    assert (result.ci_high < 0) == (result.not_worse <= (1 - LEVEL) / 2)


@given(runs(), SEEDS, st.randoms(use_true_random=False))
def test_the_order_of_the_cases_never_matters(
    pair: tuple[dict[str, float], dict[str, float]], seed: int, shuffler: object
) -> None:
    base, head = pair
    items = list(head.items())
    shuffler.shuffle(items)  # type: ignore[attr-defined]

    assert paired_bootstrap(base, dict(items), replicates=B, seed=seed, level=LEVEL) == paired_bootstrap(
        base, head, replicates=B, seed=seed, level=LEVEL
    )


@given(runs(), SEEDS, st.floats(min_value=-0.5, max_value=0.5, allow_nan=False))
def test_shifting_every_case_of_head_shifts_the_whole_result(
    pair: tuple[dict[str, float], dict[str, float]], seed: int, shift: float
) -> None:
    base, head = pair
    moved = {case: value + shift for case, value in head.items()}
    before = paired_bootstrap(base, head, replicates=B, seed=seed, level=LEVEL)
    after = paired_bootstrap(base, moved, replicates=B, seed=seed, level=LEVEL)

    assert after.delta == pytest.approx(before.delta + shift, abs=1e-9)
    assert after.ci_low == pytest.approx(before.ci_low + shift, abs=1e-9)
    assert after.ci_high == pytest.approx(before.ci_high + shift, abs=1e-9)


LEVELS = st.fractions(min_value=Fraction(1, 100), max_value=Fraction(999, 1000))


@given(LEVELS, LEVELS)
def test_more_confidence_always_leaves_a_smaller_tail(one: Fraction, other: Fraction) -> None:
    low, high = sorted((one, other))

    assert 0 < tail(high) <= tail(low) < Fraction(1, 2)
    assert tail(low) * 2 + low == 1
