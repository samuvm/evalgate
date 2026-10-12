"""Cohen's kappa between two raters over the same items, with a percentile interval (G-JUDGE-KAPPA).

kappa = (po - pe) / (1 - pe): the agreement observed, less the agreement two raters would reach by chance
given how often each of them uses each label, over the room that chance leaves. Raw agreement flatters a
judge when one label dominates: saying FIEL to everything agrees 92 % of the time with a human who says FIEL
92 % of the time, and measures nothing. Kappa is what is left after that.

**Items are resampled, each with its two labels together.** It is the same resampling of cases as
`paired_bootstrap` (R8): what one rater said about an item is never separated from what the other said about
that same item. The interval ends are the same ranks, through the same `tail`.

Exact and deterministic: the point and every replicate are fractions of integer counts, the items are put in
sorted order before any draw, and the seed is an argument.

Where both raters used a single label, and the same one, pe = 1 and kappa is 0/0. The point raises instead
of returning a flattering 1; a replicate that drew such a sample is left out of the interval and counted in
`undefined_replicates`, because with a rare label that is exactly the fragility a reader has to see.
"""

import math
import random
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from fractions import Fraction

from evalgate.stats.paired_bootstrap import tail

__all__ = ["Kappa", "KappaUndefined", "cohens_kappa"]


class KappaUndefined(ValueError):
    """Both raters used one and the same label for everything: there is no agreement beyond chance to
    measure."""


@dataclass(frozen=True, slots=True)
class Kappa:
    n: int
    replicates: int
    point: Fraction
    ci_low: Fraction
    ci_high: Fraction
    # Replicates whose sample held a single label: left out of the interval, never hidden.
    undefined_replicates: int


def _kappa(cells: Sequence[int], labels: int) -> Fraction | None:
    """(n·agreements - S) / (n² - S), with S = Σ over labels of (times the first used it) times (times the
    second did). That is (po - pe) / (1 - pe) with both sides multiplied by n². None where n² = S.

    An item is the cell of the table it falls in: `first * labels + second`, labels numbered from 0.
    """
    n = len(cells)
    table = [0] * (labels * labels)
    for cell in cells:
        table[cell] += 1
    agreements = sum(table[label * labels + label] for label in range(labels))
    chance = sum(
        sum(table[label * labels : (label + 1) * labels]) * sum(table[label::labels])
        for label in range(labels)
    )
    if chance == n * n:
        return None
    return Fraction(n * agreements - chance, n * n - chance)


def cohens_kappa(
    ratings: Mapping[str, tuple[str, str]], *, replicates: int, seed: int, level: Fraction
) -> Kappa:
    """Kappa of the two labels each item carries, and its percentile interval at `level`.

    `ratings` maps an item to (label of one rater, label of the other). Which rater comes first does not
    matter: kappa measures agreement, not which of the two is right.
    """
    if replicates < 1:
        raise ValueError(f"replicates must be at least 1, not {replicates}")
    alpha = tail(level)
    if not ratings:
        raise ValueError("no hay ítems etiquetados: no hay concordancia que medir")
    pairs = [ratings[item] for item in sorted(ratings)]
    number = {label: index for index, label in enumerate(sorted({label for pair in pairs for label in pair}))}
    cells = [number[first] * len(number) + number[second] for first, second in pairs]
    point = _kappa(cells, len(number))
    if point is None:
        raise KappaUndefined(
            f"los dos evaluadores usaron una sola clase ({pairs[0][0]}) en los {len(pairs)} ítems: "
            "la kappa no está definida"
        )

    n = len(pairs)
    rng = random.Random(seed)  # noqa: S311  # nosec B311 - resampling for statistics, not cryptography
    drawn = [_kappa(rng.choices(cells, k=n), len(number)) for _ in range(replicates)]
    defined = sorted(value for value in drawn if value is not None)
    if not defined:
        raise KappaUndefined(
            f"ninguno de los {replicates} remuestreos contiene dos clases: no hay intervalo que dar"
        )
    low_rank = math.floor(len(defined) * alpha) + 1  # 1-based, as in paired_bootstrap
    high_rank = math.ceil(len(defined) * (1 - alpha))
    return Kappa(
        n=n,
        replicates=replicates,
        point=point,
        ci_low=defined[low_rank - 1],
        ci_high=defined[high_rank - 1],
        undefined_replicates=replicates - len(defined),
    )
