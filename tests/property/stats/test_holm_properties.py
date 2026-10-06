"""Properties of Holm's correction (RULES §4.2: every public function of stats/ has a property test)."""

from fractions import Fraction

from hypothesis import given
from hypothesis import strategies as st

from evalgate.stats.holm import holm_adjust

P = st.fractions(min_value=0, max_value=1, max_denominator=10_000)
FAMILIES = st.lists(P, min_size=1, max_size=12)
ALPHAS = st.fractions(min_value=Fraction(1, 1000), max_value=Fraction(1, 5))


def step_down(p_values: list[Fraction], alpha: Fraction) -> list[bool]:
    """Holm as the textbook states it: walk the sorted p-values, reject while p_(i) <= alpha / (m - i), stop
    at the first failure. Written independently of the adjusted-p form it checks."""
    m = len(p_values)
    order = sorted(range(m), key=lambda i: p_values[i])
    rejected = [False] * m
    for rank, index in enumerate(order):
        if p_values[index] > alpha / (m - rank):
            break
        rejected[index] = True
    return rejected


@given(FAMILIES, ALPHAS)
def test_adjusted_p_values_reject_exactly_what_the_step_down_procedure_rejects(
    p_values: list[Fraction], alpha: Fraction
) -> None:
    assert [adjusted <= alpha for adjusted in holm_adjust(p_values)] == step_down(p_values, alpha)


@given(FAMILIES)
def test_adjustment_never_lowers_a_p_value_and_never_passes_one(p_values: list[Fraction]) -> None:
    for raw, adjusted in zip(p_values, holm_adjust(p_values), strict=True):
        assert raw <= adjusted <= 1


@given(FAMILIES)
def test_adjustment_keeps_the_order_of_the_evidence(p_values: list[Fraction]) -> None:
    adjusted = holm_adjust(p_values)
    for i in range(len(p_values)):
        for j in range(len(p_values)):
            if p_values[i] <= p_values[j]:
                assert adjusted[i] <= adjusted[j]


@given(FAMILIES, st.randoms(use_true_random=False))
def test_adjustment_does_not_depend_on_the_order_the_metrics_are_listed(
    p_values: list[Fraction], shuffler: object
) -> None:
    order = list(range(len(p_values)))
    shuffler.shuffle(order)  # type: ignore[attr-defined]
    shuffled = holm_adjust([p_values[i] for i in order])

    assert [shuffled[order.index(i)] for i in range(len(p_values))] == holm_adjust(p_values)


@given(FAMILIES, P)
def test_adding_a_metric_to_the_family_never_makes_another_one_easier_to_block(
    p_values: list[Fraction], extra: Fraction
) -> None:
    """The family-wise guarantee, from the side that matters for a gate: more metrics, never fewer doubts."""
    alone, together = holm_adjust(p_values), holm_adjust([*p_values, extra])

    assert all(with_more >= before for before, with_more in zip(alone, together, strict=False))
