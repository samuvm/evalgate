"""The agreement block of G-JUDGE-KAPPA, against the first batch of this project worked out by hand."""

from fractions import Fraction as F

import pytest

from evalgate.evals.metrics.agreement import agreement_block, judge_label
from evalgate.stats.kappa import KappaUndefined

LEVEL = F(95, 100)


def ratings(*cells: tuple[str, str, int]) -> dict[str, tuple[str, str]]:
    pairs = [(human, judge) for human, judge, count in cells for _ in range(count)]
    return {f"t1-{i:02d}": pair for i, pair in enumerate(pairs)}


FIRST_BATCH = ratings(("FIEL", "FIEL", 38), ("FIEL", "NO_FIEL", 8), ("NO_FIEL", "FIEL", 2), ("NO_FIEL", "NO_FIEL", 2))


@pytest.mark.parametrize(
    ("verdict", "label"),
    [
        ("FIEL", "FIEL"),
        ("NO_FIEL", "NO_FIEL"),
        ("  fiel.\n", "FIEL"),
        ("Veredicto: NO_FIEL", "NO_FIEL"),
        ("", "ILEGIBLE"),
        ("no lo sé", "ILEGIBLE"),
        ("FIEL o NO_FIEL", "ILEGIBLE"),
    ],
)
def test_a_verdict_is_read_the_way_the_metric_reads_it(verdict: str, label: str) -> None:
    assert judge_label(verdict) == label


def test_the_first_batch_by_hand() -> None:
    """38/8/2/2: agreement 40/50, kappa 6/31 (tests/unit/stats/test_kappa.py does the arithmetic)."""
    block = agreement_block(FIRST_BATCH, replicates=500, seed=42, level=LEVEL)

    assert block["point"] == pytest.approx(6 / 31)
    assert block["n"] == 50
    assert block["raw_agreement"] == pytest.approx(0.8)
    assert block["table_human_judge"] == {"FIEL": {"FIEL": 38, "NO_FIEL": 8}, "NO_FIEL": {"FIEL": 2, "NO_FIEL": 2}}
    assert block["human_prevalence"] == {"FIEL": pytest.approx(0.92), "NO_FIEL": pytest.approx(0.08)}
    low, high = block["ci95_bootstrap"]
    assert low < block["point"] < high
    assert (block["level"], block["replicates"], block["seed"]) == (0.95, 500, 42)
    assert block["undefined_replicates"] == 0


def test_an_unreadable_verdict_is_a_disagreement_not_a_missing_item() -> None:
    block = agreement_block(
        ratings(("FIEL", "FIEL", 6), ("NO_FIEL", "NO_FIEL", 3), ("FIEL", "ILEGIBLE", 1)),
        replicates=200,
        seed=1,
        level=LEVEL,
    )

    assert block["n"] == 10
    assert block["raw_agreement"] == pytest.approx(0.9)
    assert block["table_human_judge"]["FIEL"] == {"FIEL": 6, "ILEGIBLE": 1}
    assert block["point"] < 1


def test_the_block_is_the_same_whatever_order_the_items_come_in() -> None:
    backwards = dict(reversed(list(FIRST_BATCH.items())))

    assert agreement_block(backwards, replicates=300, seed=7, level=LEVEL) == agreement_block(
        FIRST_BATCH, replicates=300, seed=7, level=LEVEL
    )


def test_a_single_class_is_refused_not_reported_as_perfect() -> None:
    with pytest.raises(KappaUndefined):
        agreement_block(ratings(("FIEL", "FIEL", 20)), replicates=100, seed=1, level=LEVEL)
