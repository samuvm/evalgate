"""R8: the bootstrap is paired or it fails. This file is the one RULES names.

Why it matters, as a measurement and not as a principle: the cases of a golden set differ from each other far
more than a change moves any one of them. Resampling base and head independently mixes that between-case
spread into the difference and buries a real regression; resampling CASES keeps each one compared with
itself.
"""

import inspect
import random
from fractions import Fraction as F

import pytest

import evalgate.stats.paired_bootstrap as module
from evalgate.stats.paired_bootstrap import CaseMismatch, paired_bootstrap

LEVEL = F(95, 100)


def test_a_small_uniform_regression_is_seen_paired_and_would_be_buried_unpaired() -> None:
    """Scores spread all over [0, 1]; the change takes 0.01 off every single case. Paired, the interval is
    [-0.01, -0.01]: certain. The same data resampled independently (done here by hand, since the repo has no
    such function) gives an interval some 16 times wider than the effect, straddling zero."""
    rng = random.Random(1)  # noqa: S311 - reproducible scores for a test
    base = {f"c{i:03d}": rng.random() for i in range(200)}
    head = {case: value - 0.01 for case, value in base.items()}

    paired = paired_bootstrap(base, head, replicates=2000, seed=42, level=LEVEL)

    assert paired.ci_high < 0
    assert paired.ci_high - paired.ci_low < 1e-9

    resampler = random.Random(42)  # noqa: S311 - the unpaired resampling this test argues against
    b, h = list(base.values()), list(head.values())
    unpaired = sorted(
        sum(resampler.choices(h, k=200)) / 200 - sum(resampler.choices(b, k=200)) / 200 for _ in range(2000)
    )
    assert unpaired[50] < 0 < unpaired[1949], "unpaired, the same regression is invisible"


def test_different_case_sets_raise_instead_of_degrading_to_something_unpaired() -> None:
    with pytest.raises(CaseMismatch):
        paired_bootstrap({"a": 1.0, "b": 1.0}, {"a": 1.0}, replicates=1000, seed=1, level=LEVEL)


def test_the_module_offers_one_bootstrap_and_it_is_the_paired_one() -> None:
    """Checked on what the module EXPORTS. The shape of the source is `scripts/rules/no_unpaired_bootstrap.py`
    (AST); listing every function object here broke under mutation testing, which injects its own."""
    exported = set(module.__all__)
    callables = {name for name in exported if inspect.isfunction(getattr(module, name))}

    assert {name for name in callables if "bootstrap" in name.lower()} == {"paired_bootstrap"}
    assert not [name for name in exported if "unpaired" in name.lower() or "independent" in name.lower()]
