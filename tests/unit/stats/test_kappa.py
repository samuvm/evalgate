"""Cohen's kappa against 2x2 tables worked out by hand.

kappa = (po - pe) / (1 - pe), with po the share of items both raters label alike and pe the share they would
label alike by chance given how often each uses each label. Every expected value below is that arithmetic,
done on paper and written as an exact fraction.
"""

from fractions import Fraction as F

import pytest

from evalgate.stats.kappa import KappaUndefined, cohens_kappa

LEVEL = F(95, 100)
Y, N = "FIEL", "NO_FIEL"


def table(both_yes: int, first_only: int, second_only: int, both_no: int) -> dict[str, tuple[str, str]]:
    """Items for a 2x2 table: (first rater, second rater) = (Y,Y), (Y,N), (N,Y), (N,N), that many of each."""
    cells = [(Y, Y)] * both_yes + [(Y, N)] * first_only + [(N, Y)] * second_only + [(N, N)] * both_no
    return {f"item-{i:03d}": cell for i, cell in enumerate(cells)}


def kappa(ratings: dict[str, tuple[str, str]], seed: int = 42) -> F:
    return cohens_kappa(ratings, replicates=200, seed=seed, level=LEVEL).point


def test_the_textbook_table() -> None:
    """20 / 5 / 10 / 15 of 50. po = 35/50 = 0.7. The first says Y 25 times, the second 30:
    pe = (25*30 + 25*20) / 2500 = 0.5. kappa = 0.2 / 0.5 = 2/5."""
    assert kappa(table(20, 5, 10, 15)) == F(2, 5)


def test_the_first_batch_of_this_project() -> None:
    """38 / 8 / 2 / 2 of 50 (2026-10-12). po = 40/50. Human Y 46, judge Y 40:
    pe = (46*40 + 4*10) / 2500 = 1880/2500. kappa = (2000 - 1880) / (2500 - 1880) = 120/620 = 6/31.
    Agreement of 0.80 and a kappa of 0.19: with 46 of 50 in one class, agreeing is cheap."""
    assert kappa(table(38, 8, 2, 2)) == F(6, 31)


def test_full_agreement_over_two_classes_is_one() -> None:
    assert kappa(table(7, 0, 0, 3)) == 1


def test_agreement_at_chance_level_is_zero() -> None:
    """One item in each cell: po = 1/2 and pe = 1/2."""
    assert kappa(table(1, 1, 1, 1)) == 0


def test_systematic_disagreement_is_negative() -> None:
    """Two items, each rater says Y once and never on the same item: po = 0, pe = 1/2, kappa = -1."""
    assert kappa(table(0, 1, 1, 0)) == -1


def test_more_than_two_labels() -> None:
    """Three labels, 6 items, 4 agreements. po = 4/6. First: a 2, b 2, c 2. Second: a 3, b 2, c 1.
    pe = (2*3 + 2*2 + 2*1) / 36 = 1/3. kappa = (2/3 - 1/3) / (2/3) = 1/2."""
    ratings = {
        "1": ("a", "a"),
        "2": ("a", "a"),
        "3": ("b", "b"),
        "4": ("b", "a"),
        "5": ("c", "c"),
        "6": ("c", "b"),
    }
    assert kappa(ratings) == F(1, 2)


def test_one_class_only_is_undefined_and_says_so() -> None:
    """Both raters said Y to everything: pe = 1 and kappa is 0/0. That is not agreement measured, it is
    nothing measured, so it raises instead of returning a flattering 1."""
    with pytest.raises(KappaUndefined, match="una sola clase"):
        kappa(table(9, 0, 0, 0))


def test_no_items_is_an_error() -> None:
    with pytest.raises(ValueError, match="no hay"):
        kappa({})


def test_the_report_carries_n_and_the_replicates() -> None:
    result = cohens_kappa(table(20, 5, 10, 15), replicates=300, seed=1, level=LEVEL)

    assert (result.n, result.replicates) == (50, 300)
    assert -1 <= result.ci_low <= result.ci_high <= 1


def test_the_interval_is_the_same_bits_for_the_same_seed_and_moves_with_it() -> None:
    ratings = table(20, 5, 10, 15)
    first = cohens_kappa(ratings, replicates=500, seed=7, level=LEVEL)

    assert cohens_kappa(ratings, replicates=500, seed=7, level=LEVEL) == first
    assert cohens_kappa(ratings, replicates=500, seed=8, level=LEVEL) != first


def test_the_order_the_items_arrive_in_does_not_matter() -> None:
    ratings = table(20, 5, 10, 15)
    backwards = dict(reversed(list(ratings.items())))

    assert cohens_kappa(backwards, replicates=500, seed=7, level=LEVEL) == cohens_kappa(
        ratings, replicates=500, seed=7, level=LEVEL
    )


def test_the_interval_brackets_a_clear_agreement() -> None:
    """45 + 45 agreements and 10 disagreements of 100: kappa = 0.8, and nowhere near 0 or 1."""
    result = cohens_kappa(table(45, 5, 5, 45), replicates=2000, seed=42, level=LEVEL)

    assert result.point == F(4, 5)
    assert 0.6 < result.ci_low < 0.8 < result.ci_high < 1


def test_a_wider_level_gives_a_wider_interval() -> None:
    ratings = table(20, 5, 10, 15)
    narrow = cohens_kappa(ratings, replicates=2000, seed=42, level=F(80, 100))
    wide = cohens_kappa(ratings, replicates=2000, seed=42, level=F(99, 100))

    assert wide.ci_low < narrow.ci_low <= narrow.ci_high < wide.ci_high


def test_replicates_that_drew_a_single_class_are_counted_not_hidden() -> None:
    """9 (Y,Y) and 1 (N,N): a resample misses the lone N about a third of the time ((9/10)^10 = 0.35), and
    there kappa is undefined. Those replicates are left out of the interval and reported."""
    result = cohens_kappa(table(9, 0, 0, 1), replicates=1000, seed=42, level=LEVEL)

    assert result.point == 1
    assert 250 < result.undefined_replicates < 450
    assert (result.ci_low, result.ci_high) == (1, 1)


def test_a_typical_table_has_no_undefined_replicates() -> None:
    assert cohens_kappa(table(20, 5, 10, 15), replicates=500, seed=1, level=LEVEL).undefined_replicates == 0


def test_at_least_one_replicate_is_required() -> None:
    with pytest.raises(ValueError, match="replicates"):
        cohens_kappa(table(1, 1, 1, 1), replicates=0, seed=1, level=LEVEL)


def test_when_no_replicate_holds_two_classes_there_is_no_interval_to_give() -> None:
    """Two items, one of each class, ONE replicate: half the seeds draw the same item twice. Then there is a
    point (1) and no interval, and it says so instead of inventing [1, 1]."""

    def interval_low(seed: int) -> F | str:
        try:
            return cohens_kappa(table(1, 0, 0, 1), replicates=1, seed=seed, level=LEVEL).ci_low
        except KappaUndefined as refused:
            return str(refused)

    outcomes = {interval_low(seed) for seed in range(40)}

    assert F(1) in outcomes
    assert any(isinstance(outcome, str) and "remuestreos" in outcome for outcome in outcomes)
    assert len(outcomes) == 2
