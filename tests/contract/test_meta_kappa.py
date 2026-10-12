"""`evalgate meta kappa` on the recorded data: the published kappa is reproducible offline, and the labels,
the items and the suite are held together.

Everything runs on a COPY in a temporary root. No model is reachable: calling one fails the test.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalgate.cli import meta
from evalgate.evals.cache.cached import CacheMiss
from evalgate.evals.judges import client

from ._paths import ROOT

LABELS = "evals/golden/rag-app-v2/labels"
PUBLISHED = json.loads((ROOT / "evals" / "reports" / "meta-eval.json").read_text("utf-8"))


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative in ("prompts", "evals/golden/rag-app-v2", "evals/suites/rag-app-v2"):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "GOALS.yaml", tmp_path / "docs" / "GOALS.yaml")

    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("a recorded run called a model")

    monkeypatch.setattr(client, "chat", unreachable)
    return tmp_path


def measure(root: Path) -> dict[str, Any]:
    return meta.run(
        root / LABELS,
        root,
        root / "docs" / "GOALS.yaml",
        root / "meta-eval.json",
        refresh=False,
        base_url="http://no.such.host/v1",
    )


def test_the_published_kappa_is_what_the_recorded_data_gives(root: Path) -> None:
    """Nobody typed the number: the labels and the recorded verdicts give it again, to the last digit."""
    assert measure(root)["cohens_kappa"] == PUBLISHED["cohens_kappa"]


def test_the_measurement_is_at_least_100_items_and_every_batch_is_declared(root: Path) -> None:
    """G-JUDGE-KAPPA asks for n >= 100. Which batches count is written next to the labels, not chosen on the
    command line; a batch a judge was corrected against would be reported apart, never inside the number."""
    kappa = measure(root)["cohens_kappa"]
    plan = yaml.safe_load((root / LABELS / "kappa.yaml").read_text("utf-8"))

    assert kappa["n"] >= 100
    assert kappa["batches"] == plan["measurement"]
    assert not set(plan["measurement"]) & set(plan["development"])
    assert (kappa["development"] is None) == (not plan["development"])
    assert sum(sum(row.values()) for row in kappa["table_human_judge"].values()) == kappa["n"]
    assert len(kappa["human_prevalence"]) >= 2, "with one class there is nothing to measure"


def test_a_batch_used_to_build_the_judge_is_reported_apart(root: Path) -> None:
    path = root / LABELS / "kappa.yaml"
    path.write_text("suite: rag-app-v2\ndevelopment: [1]\nmeasurement: [2, 3]\n", "utf-8")

    kappa = measure(root)["cohens_kappa"]

    assert (kappa["batches"], kappa["n"]) == ([2, 3], 100)
    assert (kappa["development"]["batches"], kappa["development"]["n"]) == ([1], 50)


def test_a_batch_cannot_be_both_development_and_measurement(root: Path) -> None:
    path = root / LABELS / "kappa.yaml"
    path.write_text("suite: rag-app-v2\ndevelopment: [1]\nmeasurement: [1, 2]\n", "utf-8")

    with pytest.raises(meta.LabelsError, match="a la vez"):
        measure(root)


def test_the_document_names_the_judge_that_was_measured(root: Path) -> None:
    judge = measure(root)["cohens_kappa"]["judge"]
    prompt = (root / "prompts" / "judge_faithfulness.md").read_text("utf-8")

    assert f"version: {judge['prompt_version']}\n" in prompt
    assert judge["prompt_sha256"].startswith("sha256:")
    assert judge["sampling"]["temperature"] == 0.0


def test_the_other_blocks_of_the_meta_eval_document_are_kept(root: Path) -> None:
    (root / "meta-eval.json").write_text(json.dumps({"fp_rate_baseline_fixed": {"point": 0.02}}), "utf-8")

    assert measure(root)["fp_rate_baseline_fixed"] == {"point": 0.02}


def test_a_label_that_is_not_of_its_item_is_refused(root: Path) -> None:
    path = root / LABELS / "tanda-2.labels.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    rows[0]["item_sha256"] = rows[1]["item_sha256"]
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), "utf-8")

    with pytest.raises(meta.LabelsError, match="no corresponde"):
        measure(root)


def test_a_batch_that_is_not_fully_labelled_is_refused(root: Path) -> None:
    path = root / LABELS / "tanda-3.labels.jsonl"
    path.write_text("".join(path.read_text("utf-8").splitlines(keepends=True)[:-1]), "utf-8")

    with pytest.raises(meta.LabelsError, match="sin etiquetar"):
        measure(root)


def test_outputs_recorded_again_after_labelling_are_refused(root: Path) -> None:
    """A label was given on one answer. If the system's recorded answer changes, the label is of nothing."""
    path = root / "evals/suites/rag-app-v2/sut/base.jsonl"
    rows = [json.loads(line) for line in path.read_text("utf-8").splitlines()]
    for row in rows:
        row["answer"] = "otra respuesta"
    path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")

    with pytest.raises(meta.LabelsError, match="ya no es lo que se etiquetó"):
        measure(root)


def test_a_judge_that_changed_after_the_measurement_is_not_answered_from_memory(root: Path) -> None:
    """Another prompt is another judge: its verdicts are not recorded and nothing is made up for it."""
    path = root / "prompts" / "judge_faithfulness.md"
    path.write_text(path.read_text("utf-8") + "\nSé benévolo.\n", "utf-8")

    with pytest.raises(CacheMiss):
        measure(root)
