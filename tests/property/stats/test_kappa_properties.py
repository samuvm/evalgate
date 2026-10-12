"""Properties of Cohen's kappa (RULES §4.2: every public function of stats/ has a property test)."""

from fractions import Fraction

from hypothesis import assume, given
from hypothesis import strategies as st

from evalgate.stats.kappa import KappaUndefined, cohens_kappa

LEVEL = Fraction(95, 100)
LABELS = st.sampled_from(["FIEL", "NO_FIEL", "ILEGIBLE"])
RATINGS = st.dictionaries(
    st.text(alphabet="abcdefgh0123", min_size=1, max_size=4),
    st.tuples(LABELS, LABELS),
    min_size=1,
    max_size=30,
)
SEEDS = st.integers(min_value=0, max_value=2**32)


def measured(ratings: dict[str, tuple[str, str]], seed: int = 0, replicates: int = 30):  # type: ignore[no-untyped-def]
    """The kappa of `ratings`, or None where it is undefined (a single class used by both raters)."""
    try:
        return cohens_kappa(ratings, replicates=replicates, seed=seed, level=LEVEL)
    except KappaUndefined:
        return None


@given(RATINGS, SEEDS)
def test_kappa_and_its_interval_stay_between_minus_one_and_one(
    ratings: dict[str, tuple[str, str]], seed: int
) -> None:
    result = measured(ratings, seed)
    assume(result is not None)

    assert -1 <= result.point <= 1
    assert -1 <= result.ci_low <= result.ci_high <= 1
    assert 0 <= result.undefined_replicates < result.replicates


@given(RATINGS, SEEDS)
def test_swapping_the_raters_changes_nothing(ratings: dict[str, tuple[str, str]], seed: int) -> None:
    """Kappa does not know which rater is the human: it measures agreement, not correctness."""
    swapped = {item: (second, first) for item, (first, second) in ratings.items()}

    assert measured(swapped, seed) == measured(ratings, seed)


@given(RATINGS, SEEDS)
def test_renaming_the_labels_changes_nothing(ratings: dict[str, tuple[str, str]], seed: int) -> None:
    rename = {"FIEL": "x", "NO_FIEL": "y", "ILEGIBLE": "z"}
    renamed = {item: (rename[first], rename[second]) for item, (first, second) in ratings.items()}

    assert measured(renamed, seed) == measured(ratings, seed)


@given(RATINGS)
def test_kappa_is_one_exactly_when_the_raters_never_differ(ratings: dict[str, tuple[str, str]]) -> None:
    result = measured(ratings)
    assume(result is not None)

    assert (result.point == 1) == all(first == second for first, second in ratings.values())


@given(RATINGS)
def test_undefined_exactly_when_both_raters_used_one_and_the_same_label(
    ratings: dict[str, tuple[str, str]],
) -> None:
    single = len({label for pair in ratings.values() for label in pair}) == 1

    assert (measured(ratings) is None) == single


@given(RATINGS, st.integers(min_value=2, max_value=4))
def test_repeating_every_item_keeps_the_point(ratings: dict[str, tuple[str, str]], times: int) -> None:
    """Kappa is a function of proportions: the same table k times over is the same kappa."""
    result = measured(ratings)
    assume(result is not None)
    repeated = {f"{item}#{copy}": pair for item, pair in ratings.items() for copy in range(times)}

    assert measured(repeated).point == result.point
