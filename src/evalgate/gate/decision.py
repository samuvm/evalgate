"""The decision of the gate: given the evidence per metric, block or allow (retrieval-metrics.md §4).

The contract's rule, and the only thing this module knows:

    the gate blocks if a blocking metric FALLS below its absolute threshold, OR the confidence interval of
    its paired difference lies entirely on the worse side; with more than a few blocking metrics watched
    at once, after a multiple-comparison correction.

**No number is written here** (R7, `scripts/rules/no_magic_thresholds.py`): the confidence level, the size
of family that demands a correction and the correction itself arrive in `Policy`, from configuration. A
threshold in this file would be a decision nobody approved.

Two readings of the contract that are decisions, and are tested as such:

- "Falls below" means below the threshold AND worse than base. The gate judges the change: a metric already
  under its floor that stayed flat or improved is not a regression this change caused, and blocking it would
  block its own fix. It is also what makes `compare(a, a)` never block (R9).
- The family that gets corrected is the BLOCKING metrics. Metrics that are only watched are reported with
  their own evidence and never count: otherwise adding a diagnostic to a panel would make the gate deafer.

"Entirely on the worse side" is decided on the exact share of replicates in which the change was not worse
(`Bootstrap.not_worse`), compared with alpha = (1 - level) / 2. The bootstrap's interval ends are ranks built
so that this is the same statement as `ci_high < 0`, to the replicate.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from fractions import Fraction

from evalgate.stats.holm import holm_adjust
from evalgate.stats.paired_bootstrap import Bootstrap, tail

ALLOW = "pass"  # the two outcomes, as the eval-report contract spells them
BLOCK = "block"
HOLM = "holm"


@dataclass(frozen=True, slots=True)
class Policy:
    """How the gate decides. Every value comes from configuration (docs/GOALS.yaml `comparacion`): R7."""

    level: Fraction  # confidence of the interval that must lie entirely on the worse side
    correction: str | None  # multiple-comparison correction, by its contract name
    correction_above: int  # mandatory when MORE than this many blocking metrics are watched


@dataclass(frozen=True, slots=True)
class Evidence:
    """What was measured for one metric, already oriented: a positive improvement is better."""

    metric: str
    blocking: bool  # watched as blocking; the others are reported and never block
    improvement: Bootstrap  # of (head - base) in the direction that is GOOD for this metric
    breaches_absolute: bool  # head is on the wrong side of the metric's absolute threshold


@dataclass(frozen=True, slots=True)
class Verdict:
    metric: str
    blocking: bool  # this metric, by itself, blocks the change
    p_value: Fraction  # share of replicates where head was not worse; adjusted if a correction applied
    significant: bool  # the interval lies entirely on the worse side, after correction
    fell_below_absolute: bool  # breaches its absolute threshold AND got worse than base


@dataclass(frozen=True, slots=True)
class Decision:
    outcome: str  # ALLOW | BLOCK
    correction: str | None  # the correction actually applied; None when the family was small enough
    verdicts: tuple[Verdict, ...]


def _corrected(p_values: list[Fraction], policy: Policy) -> tuple[list[Fraction], str | None]:
    """The family's p-values after the correction the policy demands, and the name of what was applied."""
    if len(p_values) <= policy.correction_above:
        return p_values, None
    if policy.correction is None:
        raise ValueError(
            f"{len(p_values)} blocking metrics need a multiple-comparison correction and none is configured"
        )
    if policy.correction != HOLM:
        raise ValueError(f"correction {policy.correction!r} is not implemented by the gate; only {HOLM!r} is")
    return holm_adjust(p_values), HOLM


def decide(evidence: Sequence[Evidence], policy: Policy) -> Decision:
    """Block or allow, with the verdict of every metric in the order given."""
    seen: set[str] = set()
    for item in evidence:
        if item.metric in seen:
            raise ValueError(f"metric listed more than once: {item.metric}")
        seen.add(item.metric)

    family = [item for item in evidence if item.blocking]
    adjusted, applied = _corrected([item.improvement.not_worse for item in family], policy)
    p_of = {item.metric: p for item, p in zip(family, adjusted, strict=True)}
    alpha = tail(policy.level)

    verdicts = []
    for item in evidence:
        p_value = p_of.get(item.metric, item.improvement.not_worse)
        significant = p_value <= alpha
        fell = item.breaches_absolute and item.improvement.worse
        verdicts.append(
            Verdict(item.metric, item.blocking and (significant or fell), p_value, significant, fell)
        )
    blocked = any(verdict.blocking for verdict in verdicts)
    return Decision(BLOCK if blocked else ALLOW, applied, tuple(verdicts))
