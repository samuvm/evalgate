"""`evalgate eval self-gate` (R16, F9): the repository behind its own gate, on a copy of what it reads.

The published report is the baseline; HEAD is what the code gives from the recorded outputs. No model.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from evalgate.cli import self_gate
from evalgate.cli.main import app
from evalgate.evals.judges import client
from evalgate.gate.decision import ALLOW, BLOCK

from ._paths import ROOT

SUITE = "rag-app-v2"


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative in ("prompts", "evals/golden/rag-app-v2", f"evals/suites/{SUITE}", f"evals/reports/{SUITE}"):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    shutil.copy(ROOT / "evals/reports" / f"{SUITE}.json", tmp_path / "evals/reports" / f"{SUITE}.json")
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "GOALS.yaml", tmp_path / "docs" / "GOALS.yaml")

    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("the self gate called a model")

    monkeypatch.setattr(client, "chat", unreachable)
    return tmp_path


def _degrade(root: Path) -> None:
    """A real regression, already recorded with its verdicts: the system answers with half the context."""
    sut = root / "evals/suites" / SUITE / "sut"
    shutil.copy(sut / "contexto-50.jsonl", sut / "base.jsonl")


def test_the_repository_as_published_passes_its_own_gate(root: Path) -> None:
    comparison = self_gate.check(root, SUITE)

    assert comparison.outcome == ALLOW
    assert all(metric.delta == 0 for metric in comparison.metrics), "published and recomputed are the same"


def test_a_change_that_makes_the_system_worse_is_blocked(root: Path) -> None:
    _degrade(root)

    comparison = self_gate.check(root, SUITE)

    assert comparison.outcome == BLOCK
    blocking = {metric.rule.metric for metric in comparison.metrics if metric.verdict.blocking}
    assert "answer_correct" in blocking


def test_the_command_says_it_with_its_exit_code(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(root)
    runner = CliRunner()

    assert runner.invoke(app, ["eval", "self-gate", "--suite", SUITE]).exit_code == 0
    _degrade(root)
    blocked = runner.invoke(app, ["eval", "self-gate", "--suite", SUITE])
    assert blocked.exit_code == 1
    assert "decisión: BLOCK" in blocked.output
    assert runner.invoke(app, ["eval", "self-gate", "--suite", "no-existe"]).exit_code == 2


def test_an_answer_nobody_judged_is_not_compared(root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A recorded answer edited by hand has no recorded verdict: the run is refused (exit 2), not scored."""
    monkeypatch.chdir(root)
    path = root / "evals/suites" / SUITE / "sut" / "base.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]
    rows[0]["answer"] = "una respuesta que nadie juzgó"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")

    assert CliRunner().invoke(app, ["eval", "self-gate", "--suite", SUITE]).exit_code == 2


def test_a_report_whose_per_case_file_is_gone_cannot_be_compared_and_that_is_not_a_block(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Exit 2, never 1: a missing file is not a regression the gate found."""
    monkeypatch.chdir(root)
    (root / "evals/reports" / SUITE / "answer_correct.json").unlink()

    assert CliRunner().invoke(app, ["eval", "self-gate", "--suite", SUITE]).exit_code == 2
