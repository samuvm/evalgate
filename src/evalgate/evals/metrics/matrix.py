"""What the meta-evaluation reads from the matrix of runs (RULES §5): false positives, minimum detectable
effect and power of the gate. Pure: runs in, numbers out; the gate that is being measured is the real one.

A run is `metric → case → value`. The runs of the system against itself, with noise, are H0: nothing changed,
so every block is a false positive and every delta is noise. The runs of a degraded system are H1.

- **False positives** (G-GATE-FP): one H0 run is the fixed baseline; every other H0 run is a candidate the
  gate judges. The rate is blocks over decisions, with Wilson's interval.
- **Minimum detectable effect** (G-GATE-MDE): for each blocking metric, how much one H0 run falls below
  another, over every ordered pair of runs; its empirical percentile is the size of drop that noise alone
  rarely reaches. The gate's figure is the worst metric. In percentage points.
- **Power** (G-GATE-POWER): each run of a degraded system is judged against the same fixed baseline; power
  is blocks over runs. It is demanded of the degradations whose measured size is at least a given multiple
  of the minimum detectable effect; the smaller ones are reported and named, never hidden.

No number is decided here: the percentile, the multiple and the confidence level are arguments.
"""

import math
from collections.abc import Mapping, Sequence
from fractions import Fraction
from typing import Any

from evalgate.gate.compare import GateConfig, MetricRule, Run, compare
from evalgate.gate.decision import BLOCK
from evalgate.stats.percentile import empirical_percentile
from evalgate.stats.wilson import wilson_interval

PP = 100.0  # every metric of the suite is a share in [0, 1]; effects are published in percentage points


def _mean(run: Run, metric: str) -> float:
    values = run[metric].values()
    return math.fsum(values) / len(values)


def _blocking(rules: Sequence[MetricRule]) -> list[MetricRule]:
    blocking = [rule for rule in rules if rule.blocking]
    if not blocking:
        raise ValueError("the gate has no blocking metric: there is nothing whose effect to measure")
    return blocking


def _drop_pp(rule: MetricRule, before: float, after: float) -> float:
    """How much WORSE `after` is than `before` for this metric, in points. Negative: it got better."""
    return (before - after if rule.higher_is_better else after - before) * PP


def decisions(
    baseline: Run, candidates: Mapping[str, Run], config: GateConfig
) -> dict[str, dict[str, Any]]:
    """The gate's decision on every candidate against the one baseline: outcome and the metrics that blocked."""
    judged: dict[str, dict[str, Any]] = {}
    for run_id in sorted(candidates):
        comparison = compare(baseline, candidates[run_id], config)
        judged[run_id] = {
            "outcome": comparison.outcome,
            "blocked_by": [metric.rule.metric for metric in comparison.metrics if metric.verdict.blocking],
        }
    return judged


def _rate(judged: Mapping[str, Mapping[str, Any]], level: Fraction) -> dict[str, Any]:
    if not judged:
        raise ValueError("no decisions: a rate over nothing is not a rate")
    blocked = sorted(run_id for run_id, decision in judged.items() if decision["outcome"] == BLOCK)
    low, high = wilson_interval(len(blocked), len(judged), level)
    by_metric: dict[str, int] = {}
    for run_id in blocked:
        for metric in judged[run_id]["blocked_by"]:
            by_metric[metric] = by_metric.get(metric, 0) + 1
    return {
        "point": len(blocked) / len(judged),
        "wilson_95": [low, high],
        "level": float(level),
        "blocked": len(blocked),
        "n": len(judged),
        "blocked_runs": blocked,
        "blocked_by_metric": dict(sorted(by_metric.items())),
    }


def false_positive_block(
    h0: Mapping[str, Run], baseline: str, config: GateConfig
) -> dict[str, Any]:
    """G-GATE-FP: the share of H0 runs the gate blocks against the fixed baseline."""
    if baseline not in h0:
        raise ValueError(f"the baseline {baseline!r} is not one of the H0 runs")
    candidates = {run_id: run for run_id, run in h0.items() if run_id != baseline}
    return {**_rate(decisions(h0[baseline], candidates, config), config.policy.level), "baseline": baseline}


def mde_block(h0: Mapping[str, Run], rules: Sequence[MetricRule], percent: Fraction) -> dict[str, Any]:
    """G-GATE-MDE: the `percent` percentile of the drop between two H0 runs, worst blocking metric, in points."""
    if len(h0) < 2:  # noqa: PLR2004 - a pair
        raise ValueError("at least two H0 runs are needed to see any noise")
    run_ids = sorted(h0)
    per_metric: dict[str, dict[str, float]] = {}
    for rule in _blocking(rules):
        means = {run_id: _mean(h0[run_id], rule.metric) for run_id in run_ids}
        drops = [
            _drop_pp(rule, means[before], means[after])
            for before in run_ids
            for after in run_ids
            if before != after
        ]
        per_metric[rule.metric] = {
            "point": empirical_percentile(drops, percent),
            "max": max(drops),
            "h0_mean": math.fsum(means.values()) / len(means),
        }
    limiting = max(sorted(per_metric), key=lambda metric: per_metric[metric]["point"])
    return {
        "point": per_metric[limiting]["point"],
        "limiting_metric": limiting,
        "percentile": float(percent),
        "per_metric": per_metric,
        "n_runs": len(run_ids),
        "n_pairs": len(run_ids) * (len(run_ids) - 1),
    }


def degradation_size(
    h0: Mapping[str, Run], degraded: Mapping[str, Run], rules: Sequence[MetricRule]
) -> dict[str, Any]:
    """How big a degradation is: the drop of each blocking metric from the H0 runs to the degraded ones, on
    average, in points. Its size is the metric it hurts most."""
    if not h0 or not degraded:
        raise ValueError("a size needs runs on both sides")
    per_metric = {
        rule.metric: _drop_pp(
            rule,
            math.fsum(_mean(run, rule.metric) for run in h0.values()) / len(h0),
            math.fsum(_mean(run, rule.metric) for run in degraded.values()) / len(degraded),
        )
        for rule in _blocking(rules)
    }
    metric = max(sorted(per_metric), key=lambda name: per_metric[name])
    return {"size_pp": per_metric[metric], "size_metric": metric, "drop_pp_per_metric": per_metric}


def power_block(
    h0: Mapping[str, Run],
    baseline: str,
    degradations: Mapping[str, Mapping[str, Run]],
    config: GateConfig,
    *,
    mde_pp: float,
    min_size_over_mde: Fraction,
) -> dict[str, Any]:
    """G-GATE-POWER: the share of degraded runs the gate blocks, per degradation, and the minimum over the
    degradations big enough to be demanded (size >= `min_size_over_mde` · `mde_pp`)."""
    if baseline not in h0:
        raise ValueError(f"the baseline {baseline!r} is not one of the H0 runs")
    if not degradations:
        raise ValueError("no degradations: power against nothing is not power")
    required_size = float(min_size_over_mde) * mde_pp
    per_degradation: dict[str, dict[str, Any]] = {}
    for name in sorted(degradations):
        rate = _rate(decisions(h0[baseline], degradations[name], config), config.policy.level)
        size = degradation_size(h0, degradations[name], config.rules)
        per_degradation[name] = {
            "power": rate["point"],
            **{key: rate[key] for key in ("wilson_95", "blocked", "n", "blocked_by_metric")},
            **size,
            "big_enough": size["size_pp"] >= required_size,
        }
    demanded = [name for name, block in per_degradation.items() if block["big_enough"]]
    return {
        # None when no degradation is big enough: the gate was not shown anything it is asked to see.
        "min_over_degradations": min((per_degradation[name]["power"] for name in demanded), default=None),
        "min_over_all": min(block["power"] for block in per_degradation.values()),
        "per_degradation": per_degradation,
        "required_size_pp": required_size,
        "min_size_over_mde": float(min_size_over_mde),
        "mde_pp": mde_pp,
        "below_required_size": sorted(set(per_degradation) - set(demanded)),
        "baseline": baseline,
    }
