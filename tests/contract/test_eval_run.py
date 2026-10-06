"""The eval engine on its recorded data: `make eval`, held from outside.

Everything runs on a COPY of the suite in a temporary root, from the outputs and verdicts recorded in the
repository. No model is reachable from here, and a test makes sure none is asked.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from evalgate.cli import eval_run
from evalgate.evals.cache.cached import CacheMiss
from evalgate.evals.judges import client
from evalgate.evals.suite import SuiteError
from evalgate.gate.compare import compare
from evalgate.gate.config import gate_config

from ._paths import ROOT

SCHEMA = json.loads((ROOT / "docs" / "CONTRACTS" / "eval-report.schema.json").read_text("utf-8"))
METRICS = {"answer_correct", "context_recall", "abstencion_incorrecta", "faithfulness", "juez_ilegible"}


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A private copy of what a recorded run reads. And no model: calling one fails the test."""
    for relative in ("prompts", "evals/golden/rag-app-v1", "evals/suites/rag-app"):
        shutil.copytree(ROOT / relative, tmp_path / relative)

    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a recorded run called a model")

    monkeypatch.setattr(client, "chat", unreachable)
    return tmp_path


def recorded(root: Path) -> tuple[dict[str, Any], Any]:
    out = root / "reports"
    out.mkdir(exist_ok=True)
    return eval_run.run(
        root / "evals/suites/rag-app", root, out, refresh=False, base_url="http://no.such.host/v1"
    )


def test_the_recorded_run_scores_all_200_cases_without_calling_a_model(root: Path) -> None:
    report, stats = recorded(root)

    assert [
        e.message for e in Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(report)
    ] == []
    assert {metric["id"] for metric in report["metrics"]} == METRICS
    assert (report["dataset"]["n_cases"], report["dataset"]["n_negative_cases"]) == (200, 30)
    assert report["environment"]["deterministic"] is True
    assert (stats.misses, stats.hits) == (0, 200)


def test_the_judge_and_the_generator_of_the_real_suite_are_different_models(root: Path) -> None:
    """R12, on the suite that actually ships."""
    report, _ = recorded(root)

    models = report["environment"]["models"]
    assert models["judge"] != models["generator"]
    assert report["prompts"][0]["role"] == "judge"


def test_g_cache_hit_the_second_run_costs_nothing_of_what_the_cold_one_cost(root: Path) -> None:
    """G-CACHE-HIT as the goal defines it: run twice, read the marginal cost of the second."""
    recorded(root)
    recorded(root)

    stats = eval_run.cache_stats("rag-app", root, root / "cache-stats.json")

    assert stats["second_run"]["marginal_cost_ratio"] == 0.0
    assert stats["second_run"]["saved_tokens"] > 0
    assert json.loads((root / "cache-stats.json").read_text("utf-8")) == stats


def test_two_recorded_runs_are_the_same_run(root: Path) -> None:
    first, _ = recorded(root)
    second, _ = recorded(root)

    assert first["run_id"] == second["run_id"]
    assert first["metrics"] == second["metrics"]


def test_changing_the_judges_prompt_invalidates_the_cache_instead_of_serving_old_verdicts(root: Path) -> None:
    """The bug a cache key exists to prevent, end to end: a new prompt version must not be answered with the
    verdicts of the old one. A recorded run stops and says how to refresh."""
    prompt = root / "prompts" / "judge_faithfulness.md"
    prompt.write_text(prompt.read_text("utf-8").replace("version: 1", "version: 2"), "utf-8")

    with pytest.raises(CacheMiss, match="eval-refresh"):
        recorded(root)


def test_a_suite_pointed_at_the_judges_own_model_is_refused_before_anything_runs(root: Path) -> None:
    suite = root / "evals/suites/rag-app/suite.yaml"
    node = yaml.safe_load(suite.read_text("utf-8"))
    node["sut"]["model"] = "gemma4:12b-mlx"
    suite.write_text(yaml.safe_dump(node), "utf-8")

    with pytest.raises(SuiteError, match="R12"):
        recorded(root)


def test_the_report_of_a_run_is_what_the_gate_reads_and_a_run_against_itself_passes(root: Path) -> None:
    """F5 feeds F6: the per-case files the report points to are the input of `compare`."""
    report, _ = recorded(root)
    run = {
        metric["id"]: {
            row["case_id"]: row["value"]
            for row in json.loads((root / "reports" / metric["raw_path"]).read_text())
        }
        for metric in report["metrics"]
    }
    goals = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text("utf-8"))
    rules = yaml.safe_load((root / "evals/suites/rag-app/gate.yaml").read_text("utf-8"))["metrics"]

    result = compare(run, run, gate_config(goals["comparacion"], rules))

    assert result.outcome == "pass"
    assert {metric.rule.metric for metric in result.metrics} == METRICS
