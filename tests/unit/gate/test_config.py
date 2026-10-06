"""The gate's parameters come from configuration, and a configuration the contract forbids is refused.

`comparacion` is the block of docs/GOALS.yaml; `rules` is what a suite declares about its metrics. The real
GOALS.yaml is loaded in one test on purpose: if someone changes the block's shape, this fails here and not at
the first `eval compare` of a Friday.
"""

from fractions import Fraction as F
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalgate.gate.compare import MetricRule
from evalgate.gate.config import GateConfigError, gate_config, report_digest
from evalgate.gate.decision import Policy

ROOT = Path(__file__).resolve().parents[3]
COMPARACION: dict[str, Any] = {
    "metodo": "bootstrap",
    "pareado": True,
    "n_resamples": 10000,
    "semilla": 42,
    "correccion_multiple": "holm",
}
RULES: list[dict[str, Any]] = [
    {"id": "faithfulness", "blocking": True, "absolute": 0.85},
    {"id": "alucinacion", "blocking": True, "higher_is_better": False, "absolute": 0.0},
    {"id": "longitud", "blocking": False},
]


def test_the_block_of_goals_and_the_rules_of_a_suite_become_the_gate_config() -> None:
    config = gate_config(COMPARACION, RULES)

    assert config is not None
    assert (config.replicates, config.seed) == (10000, 42)
    # 95 % and "more than three" are the contract's (retrieval-metrics §4), until GOALS.yaml carries them.
    assert config.policy == Policy(level=F(95, 100), correction="holm", correction_above=3)
    assert config.rules == (
        MetricRule("faithfulness", blocking=True, higher_is_better=True, absolute=0.85),
        MetricRule("alucinacion", blocking=True, higher_is_better=False, absolute=0.0),
        MetricRule("longitud", blocking=False, higher_is_better=True, absolute=None),
    )


def test_the_real_goals_file_configures_the_gate() -> None:
    goals = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text("utf-8"))

    config = gate_config(goals["comparacion"], RULES)

    assert config is not None
    assert (config.replicates, config.seed, config.policy.correction) == (
        goals["comparacion"]["n_resamples"],
        goals["comparacion"]["semilla"],
        "holm",
    )


def test_goals_may_carry_the_level_and_the_family_size_and_then_they_win() -> None:
    """The day `comparacion` declares them, nothing in the code decides them."""
    config = gate_config({**COMPARACION, "nivel_confianza": 0.99, "correccion_desde": 5}, RULES)

    assert config is not None
    assert (config.policy.level, config.policy.correction_above) == (F(99, 100), 5)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"pareado": False}, "pareado"),
        ({"metodo": "permutacion"}, "metodo"),
        ({"n_resamples": 999}, "n_resamples"),
        ({"n_resamples": "muchas"}, "n_resamples"),
        ({"semilla": None}, "semilla"),
        ({"correccion_multiple": "bonferroni"}, "correccion_multiple"),
        ({"nivel_confianza": 1.0}, "nivel_confianza"),
        ({"nivel_confianza": 0}, "nivel_confianza"),
        ({"correccion_desde": -1}, "correccion_desde"),
    ],
)
def test_a_comparison_block_the_contract_forbids_is_refused(change: dict[str, Any], reason: str) -> None:
    """An unpaired bootstrap by configuration is still an unpaired bootstrap (R8)."""
    with pytest.raises(GateConfigError, match=reason):
        gate_config({**COMPARACION, **change}, RULES)


@pytest.mark.parametrize("missing", ["metodo", "pareado", "n_resamples", "semilla"])
def test_a_missing_parameter_is_not_filled_in_with_a_default(missing: str) -> None:
    block = {key: value for key, value in COMPARACION.items() if key != missing}

    with pytest.raises(GateConfigError, match=missing):
        gate_config(block, RULES)


@pytest.mark.parametrize(
    ("rules", "reason"),
    [
        ([], "rules"),
        ([{"blocking": True}], "id"),
        ([{"id": "m"}], "blocking"),
        ([{"id": "m", "blocking": "si"}], "blocking"),
        ([{"id": "m", "blocking": True, "absolute": "alto"}], "absolute"),
        ([{"id": "m", "blocking": True, "higher_is_better": "claro"}], "higher_is_better"),
        ([{"id": "m", "blocking": True, "absolute": True}], "absolute"),
        ([{"id": "m", "blocking": True, "umbral": 0.9}], "umbral"),
        ([{"id": "m", "blocking": True}, {"id": "m", "blocking": False}], "m"),
    ],
)
def test_metric_rules_that_do_not_say_what_they_mean_are_refused(
    rules: list[dict[str, Any]], reason: str
) -> None:
    with pytest.raises(GateConfigError, match=reason):
        gate_config(COMPARACION, rules)


# --- the digest two runs of `eval compare` must share (G-DETERMINISM) ---------------------------------

REPORT: dict[str, Any] = {
    "run_id": "r1",
    "created_at": "2026-10-06T10:00:00+00:00",
    "environment": {"python": "3.12", "timing": {"wall_s": 1.5}},
    "metrics": [{"id": "a", "value": 0.5}],
}
EXCLUDED = ["$.created_at", "$.environment.timing"]


def test_the_digest_ignores_exactly_the_excluded_fields() -> None:
    later = {
        **REPORT,
        "created_at": "2027-01-01T00:00:00+00:00",
        "environment": {"python": "3.12", "timing": {"wall_s": 99.0}},
    }

    assert report_digest(REPORT, EXCLUDED) == report_digest(later, EXCLUDED)


def test_anything_else_that_changes_changes_the_digest() -> None:
    other_value = {**REPORT, "metrics": [{"id": "a", "value": 0.5000001}]}
    other_env = {**REPORT, "environment": {"python": "3.13", "timing": {"wall_s": 1.5}}}

    assert len({report_digest(d, EXCLUDED) for d in (REPORT, other_value, other_env)}) == 3


def test_the_digest_does_not_depend_on_key_order_and_does_not_touch_the_document() -> None:
    reordered = dict(reversed(list(REPORT.items())))
    before = repr(REPORT)

    assert report_digest(reordered, EXCLUDED) == report_digest(REPORT, EXCLUDED)
    assert repr(REPORT) == before


def test_an_excluded_field_that_is_absent_is_not_an_error_and_a_path_it_cannot_read_is() -> None:
    assert report_digest({"run_id": "r"}, EXCLUDED) == report_digest({"run_id": "r"}, [])
    with pytest.raises(GateConfigError, match="metrics"):
        report_digest(REPORT, ["$.metrics[0].value"])
