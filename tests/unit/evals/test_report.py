"""The report of a run: valid against the shared contract, traceable to its prompt (R14), and written so the
gate can read it back (`metrics[].raw_path` → the per-case values `eval compare` pairs).
"""

import json
import math
from pathlib import Path
from typing import Any

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from evalgate.evals.cache.store import CacheStats
from evalgate.evals.prompts import Prompt
from evalgate.evals.report import eval_report, raw_rows
from evalgate.evals.suite import Suite

ROOT = Path(__file__).resolve().parents[3]
SCHEMA = json.loads((ROOT / "docs" / "CONTRACTS" / "eval-report.schema.json").read_text("utf-8"))
PROMPT = Prompt("judge_faithfulness", 2, "gemma4:12b-mlx", 0.0, "v2", "Eres...\n", "ab" * 32)
SUITE = Suite("rag-app", "evals/golden/rag-app-v1", "qwen3.5:9b-mlx", "faithfulness", PROMPT,
              {"temperature": 0.0, "seed": 7}, "sut/base.jsonl", "cache.jsonl")
SCORES = {
    "answer_correct": {"gs-1": 1.0, "gs-2": 0.0, "gs-3": 1.0, "gs-4": 1.0},
    "context_recall": {"gs-1": 1.0, "gs-2": 0.5},
}
FACTS: dict[str, Any] = {
    "golden_sha256": "sha256:" + "0" * 64,
    "sut_outputs_sha256": "sha256:" + "1" * 64,
    "n_cases": 4,
    "n_negative_cases": 2,
    "hardware": "arm64 · macOS",
    "python": "3.12.12",
    "deterministic": True,
    "created_at": "2026-10-07T10:00:00+00:00",
    "raw_dir": "rag-app",
}
STATS = CacheStats(hits=3, misses=1, spent_tokens=100, saved_tokens=300)


def test_the_report_honours_the_shared_contract() -> None:
    report = eval_report(SUITE, SCORES, STATS, FACTS)

    assert [e.message for e in Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(report)] == []
    assert (report["project"], report["suite"], report["contract_version"]) == ("evalgate", "rag-app", 1)


def test_each_metric_is_the_mean_of_its_cases_with_its_own_denominator() -> None:
    report = eval_report(SUITE, SCORES, STATS, FACTS)

    by_id = {metric["id"]: metric for metric in report["metrics"]}
    assert (by_id["answer_correct"]["value"], by_id["answer_correct"]["n"]) == (0.75, 4)
    # Only the two positive cases entered this one: `n` is the metric's denominator, not the suite's size.
    assert (by_id["context_recall"]["value"], by_id["context_recall"]["n"]) == (0.75, 2)
    assert by_id["context_recall"]["raw_path"] == "rag-app/context_recall.json"
    assert by_id["answer_correct"]["unit"] == "ratio"


def test_the_report_names_every_prompt_with_version_and_digest_and_who_played_which_role() -> None:
    """R14: without {id, version, sha256} a change in a metric cannot be traced to a change in a prompt."""
    report = eval_report(SUITE, SCORES, STATS, FACTS)

    assert report["prompts"] == [
        {"id": "judge_faithfulness", "version": 2, "sha256": "sha256:" + "ab" * 32, "role": "judge"}
    ]
    assert report["environment"]["models"] == {"generator": "qwen3.5:9b-mlx", "judge": "gemma4:12b-mlx"}
    assert report["environment"]["deterministic"] is True
    assert report["environment"]["seed"] == 7


def test_the_dataset_block_identifies_the_golden_set_the_gate_will_insist_on() -> None:
    report = eval_report(SUITE, SCORES, STATS, FACTS)

    assert report["dataset"] == {
        "name": "rag-app-v1",
        "version": 1,
        "n_cases": 4,
        "n_negative_cases": 2,
        "sha256": "sha256:" + "0" * 64,
    }


def test_the_cache_block_declares_what_was_saved_instead_of_estimating_it() -> None:
    report = eval_report(SUITE, SCORES, STATS, FACTS)

    assert report["cache"] == {"judge_hits": 3, "judge_misses": 1, "savings_ratio": 0.75}


def test_the_run_id_is_the_same_for_the_same_inputs_and_changes_with_any_of_them() -> None:
    """Deterministic if the run is. The cache statistics and the clock are NOT inputs: a warm and a cold run
    of the same suite over the same outputs are the same run."""
    base = eval_report(SUITE, SCORES, STATS, FACTS)["run_id"]

    assert eval_report(SUITE, SCORES, CacheStats(4, 0, 0, 400), {**FACTS, "created_at": "2030-01-01T00:00:00+00:00"})[
        "run_id"
    ] == base
    assert eval_report(SUITE, SCORES, STATS, {**FACTS, "sut_outputs_sha256": "sha256:" + "2" * 64})["run_id"] != base
    assert eval_report(SUITE, SCORES, STATS, {**FACTS, "golden_sha256": "sha256:" + "3" * 64})["run_id"] != base
    other_prompt = Suite(**{**{f: getattr(SUITE, f) for f in SUITE.__slots__}, "judge_prompt": Prompt(
        "judge_faithfulness", 3, "gemma4:12b-mlx", 0.0, "v3", "Eres...\n", "cd" * 32)})
    assert eval_report(other_prompt, SCORES, STATS, FACTS)["run_id"] != base


def test_raw_rows_are_what_eval_compare_reads_back_in_case_order() -> None:
    rows = raw_rows({"m": {"gs-2": 0.0, "gs-1": 1.0}})

    assert rows == {"m": [{"case_id": "gs-1", "value": 1.0}, {"case_id": "gs-2", "value": 0.0}]}


def test_a_metric_with_no_cases_is_refused_rather_than_reported_as_nan() -> None:
    with pytest.raises(ValueError, match="vacia"):
        eval_report(SUITE, {"vacia": {}}, STATS, FACTS)
    assert not math.isnan(eval_report(SUITE, SCORES, STATS, FACTS)["metrics"][0]["value"])
