"""Comparison of two runs, metric by metric, and the `comparison` block of the eval report.

`compare` turns two runs (per metric, the value of every case) and the rules of the gate into the evidence
`decision.decide` judges. It adds no judgement of its own; what it owns is ORIENTATION and bookkeeping:

- A metric where lower is better (a hallucination rate) is resampled with the runs swapped, so the decision
  always sees "positive is better". The report keeps the delta and the interval in the metric's own sign, as
  measured: a rate that went up is reported as a positive delta, and blocks.
- Every metric is resampled with its own seed, derived from the configured one and the metric's name. The
  numbers of a metric then depend on that metric alone: listing one more metric cannot move another's
  interval, which is half of G-DETERMINISM and what lets two reports be compared line by line.
- A rule without its metric in a run, runs over different cases, or a gate with no rules are errors. Each
  one, skipped quietly, is a gate that passes what nobody measured.
"""

import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from evalgate.gate.decision import Evidence, Policy, Verdict, decide
from evalgate.stats.paired_bootstrap import paired_bootstrap

Run = Mapping[str, Mapping[str, float]]  # metric → case → value


class MissingMetric(ValueError):
    """A run lacks a metric the gate was told to judge. Skipping it would pass what nobody measured."""


@dataclass(frozen=True, slots=True)
class MetricRule:
    metric: str
    blocking: bool
    higher_is_better: bool = True
    absolute: float | None = None  # the floor if higher is better, the ceiling if lower is


@dataclass(frozen=True, slots=True)
class GateConfig:
    replicates: int
    seed: int
    policy: Policy
    rules: tuple[MetricRule, ...]


@dataclass(frozen=True, slots=True)
class MetricComparison:
    rule: MetricRule
    base_value: float
    head_value: float
    delta: float  # head - base, in the metric's own units and sign
    ci_low: float
    ci_high: float
    breaches_absolute: bool
    verdict: Verdict


@dataclass(frozen=True, slots=True)
class Comparison:
    outcome: str
    correction: str | None
    replicates: int
    seed: int
    metrics: tuple[MetricComparison, ...]


def metric_seed(seed: int, metric: str) -> int:
    """The seed of one metric's resampling: stable across runs and machines, different per metric."""
    return int.from_bytes(hashlib.sha256(f"{seed}:{metric}".encode()).digest()[:8], "big")


def _values(run: Run, metric: str, which: str) -> Mapping[str, float]:
    if metric not in run:
        raise MissingMetric(f"the {which} run has no metric {metric!r}, and the gate is told to judge it")
    return run[metric]


def _mean(values: Mapping[str, float]) -> float:
    return math.fsum(values.values()) / len(values) if values else math.nan


def _flip(value: float) -> float:
    """Sign reversed, with zero staying a plain 0.0: `-0.0` equals 0 and prints differently in a report."""
    return 0.0 - value


def _one(rule: MetricRule, base: Run, head: Run, config: GateConfig) -> tuple[MetricComparison, Evidence]:
    base_cases, head_cases = _values(base, rule.metric, "base"), _values(head, rule.metric, "head")
    seed = metric_seed(config.seed, rule.metric)
    level = config.policy.level
    if rule.higher_is_better:
        improvement = paired_bootstrap(
            base_cases, head_cases, replicates=config.replicates, seed=seed, level=level
        )
        delta, low, high = improvement.delta, improvement.ci_low, improvement.ci_high
    else:
        # Swapped: improvement = base - head. Mirrored back for the report, which speaks the metric's sign.
        improvement = paired_bootstrap(
            head_cases, base_cases, replicates=config.replicates, seed=seed, level=level
        )
        delta, low, high = _flip(improvement.delta), _flip(improvement.ci_high), _flip(improvement.ci_low)
    head_value = _mean(head_cases)
    breaches = rule.absolute is not None and (
        head_value < rule.absolute if rule.higher_is_better else head_value > rule.absolute
    )
    evidence = Evidence(rule.metric, rule.blocking, improvement, breaches)
    # The verdict is filled in by `compare`, once the whole family has been judged together.
    pending = Verdict(
        rule.metric,
        blocking=False,
        p_value=improvement.not_worse,
        significant=False,
        fell_below_absolute=False,
    )
    return MetricComparison(
        rule, _mean(base_cases), head_value, delta, low, high, breaches, pending
    ), evidence


def compare(base: Run, head: Run, config: GateConfig) -> Comparison:
    """Judge `head` against `base` under `config`. Raises instead of comparing what cannot be compared."""
    if not config.rules:
        raise ValueError("the gate has no rules: with nothing to judge it would pass anything")
    measured = [_one(rule, base, head, config) for rule in config.rules]
    decision = decide([evidence for _, evidence in measured], config.policy)
    metrics = tuple(
        replace(metric, verdict=verdict)
        for (metric, _), verdict in zip(measured, decision.verdicts, strict=True)
    )
    return Comparison(decision.outcome, decision.correction, config.replicates, config.seed, metrics)


def comparison_block(comparison: Comparison, base_run_id: str) -> dict[str, Any]:
    """The `comparison` object of docs/CONTRACTS/eval-report.schema.json, field for field."""
    return {
        "base_run_id": base_run_id,
        "method": {
            "kind": "bootstrap",
            "paired": True,
            "replicates": comparison.replicates,
            "multiple_comparison_correction": comparison.correction,
        },
        "deltas": [
            {
                "id": metric.rule.metric,
                "delta": metric.delta,
                "ci95": [metric.ci_low, metric.ci_high],
                "below_absolute_threshold": metric.breaches_absolute,
                "blocking": metric.verdict.blocking,
            }
            for metric in comparison.metrics
        ],
        "decision": comparison.outcome,
    }
