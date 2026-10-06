"""The report `evalgate eval compare` writes, held to the shared contract. This is the file RULES R8 names.

Run through the real command (typer's runner), on the declared synthetic fixture whose answers were written
down before the gate existed (`evals/suites/compare-fixture/expected.yaml`).
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker
from typer.testing import CliRunner

from evalgate.cli.main import app
from evalgate.gate.config import report_digest

from ._paths import ROOT

SUITE = ROOT / "evals" / "suites" / "compare-fixture"
SCHEMA = json.loads((ROOT / "docs" / "CONTRACTS" / "eval-report.schema.json").read_text("utf-8"))
GOALS = yaml.safe_load((ROOT / "docs" / "GOALS.yaml").read_text("utf-8"))
EXPECTED: dict[str, str] = yaml.safe_load((SUITE / "expected.yaml").read_text("utf-8"))
EXCLUDED = [
    e["path"]
    for e in yaml.safe_load((ROOT / "evals" / "report-hash-exclusions.yaml").read_text("utf-8"))["exclusions"]
]
EXIT = {"pass": 0, "block": 1}


def compared(head: str, out: Path, suite: Path = SUITE) -> tuple[int, dict[str, Any], str]:
    result = CliRunner().invoke(
        app,
        [
            "eval",
            "compare",
            str(suite / "base.json"),
            str(suite / f"{head}.json"),
            "--gate",
            str(suite / "gate.yaml"),
            "--out",
            str(out),
            "--goals",
            str(ROOT / "docs" / "GOALS.yaml"),
        ],
    )
    document = json.loads(out.read_text("utf-8")) if out.exists() else {}
    return result.exit_code, document, result.output


@pytest.mark.parametrize("head", sorted(EXPECTED))
def test_the_gate_decides_what_was_written_down_before_it_ran(head: str, tmp_path: Path) -> None:
    exit_code, document, output = compared(head, tmp_path / "out.json")

    assert document["comparison"]["decision"] == EXPECTED[head]
    assert exit_code == EXIT[EXPECTED[head]]
    assert f"decisión: {EXPECTED[head].upper()}" in output


@pytest.mark.parametrize("head", sorted(EXPECTED))
def test_the_comparison_report_honours_the_eval_report_contract(head: str, tmp_path: Path) -> None:
    _, document, _ = compared(head, tmp_path / "out.json")

    errors = [
        e.message for e in Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(document)
    ]
    assert errors == []


def test_multiple_comparison_correction_is_holm_literally_and_matches_goals(tmp_path: Path) -> None:
    """R8: with more than three blocking metrics watched, every emitted report writes "holm", and it is the
    value docs/GOALS.yaml declares, not one the code prefers."""
    _, document, _ = compared("head-regresion", tmp_path / "out.json")
    rules = yaml.safe_load((SUITE / "gate.yaml").read_text("utf-8"))["metrics"]

    assert sum(rule["blocking"] for rule in rules) > 3
    assert document["comparison"]["method"]["multiple_comparison_correction"] == "holm"
    assert (
        document["comparison"]["method"]["multiple_comparison_correction"]
        == GOALS["comparacion"]["correccion_multiple"]
    )
    assert document["comparison"]["method"] == {
        "kind": "bootstrap",
        "paired": True,
        "replicates": GOALS["comparacion"]["n_resamples"],
        "multiple_comparison_correction": "holm",
    }
    assert document["environment"]["seed"] == GOALS["comparacion"]["semilla"]


def test_the_regression_is_blocked_by_the_metrics_that_regressed_and_only_those(tmp_path: Path) -> None:
    _, document, output = compared("head-regresion", tmp_path / "out.json")

    blocking = {delta["id"] for delta in document["comparison"]["deltas"] if delta["blocking"]}
    assert blocking == {"faithfulness", "alucinacion"}
    assert "BLOQUEA" in output


def test_two_runs_over_the_same_reports_share_decision_and_digest(tmp_path: Path) -> None:
    """G-DETERMINISM, in process. `make eval-compare-twice` does it across two separate processes."""
    for head in EXPECTED:
        _, first, _ = compared(head, tmp_path / "a.json")
        _, second, _ = compared(head, tmp_path / "b.json")

        assert first["comparison"] == second["comparison"]
        assert first["run_id"] == second["run_id"]
        assert report_digest(first, EXCLUDED) == report_digest(second, EXCLUDED)


def test_reports_over_different_datasets_are_refused_with_exit_2_and_no_report(tmp_path: Path) -> None:
    """The contract: comparing two reports over different datasets means nothing, and the gate must refuse."""
    suite = Path(shutil.copytree(SUITE, tmp_path / "suite"))
    head = suite / "head-igual.json"
    document = json.loads(head.read_text("utf-8"))
    document["dataset"]["sha256"] = "sha256:" + "0" * 64
    head.write_text(json.dumps(document), "utf-8")

    exit_code, written, output = compared("head-igual", tmp_path / "out.json", suite)

    assert exit_code == 2
    assert written == {}
    assert "dataset.sha256" in output


def test_a_head_measured_over_other_cases_is_refused_not_compared_unpaired(tmp_path: Path) -> None:
    suite = Path(shutil.copytree(SUITE, tmp_path / "suite"))
    raw = suite / "head-igual" / "faithfulness.json"
    rows = json.loads(raw.read_text("utf-8"))
    rows[0]["case_id"] = "caso-que-no-estaba"
    raw.write_text(json.dumps(rows), "utf-8")

    exit_code, written, output = compared("head-igual", tmp_path / "out.json", suite)

    assert (exit_code, written) == (2, {})
    assert "caso-que-no-estaba" in output
