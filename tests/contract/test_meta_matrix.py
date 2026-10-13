"""`evalgate meta run-matrix --build-only | fp | mde | sensitivity` end to end, on a small matrix.

The runs are not executed: their files are written here from the suite's RECORDED outputs (the base system
and one degradation), which is exactly the shape `run-matrix` records. No model is reachable.
"""

import json
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from evalgate.cli import matrix, meta
from evalgate.evals.judges import client

from ._paths import ROOT

SUITE = "evals/suites/rag-app-v2"
PLAN = """\
suite: rag-app-v2
cases: evals/golden/rag-app-v2/calibracion.json
noise: { RAG_TEMPERATURE: "0.7" }
seed_from: 1000
runs: { base: 3, contexto-50: 2 }
baseline: base-00
mde_percentile: 95
power_min_size_over_mde: 1.5
"""


def _rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text("utf-8").splitlines() if line.strip()]


@pytest.fixture
def root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    for relative in ("prompts", "evals/golden/rag-app-v2", SUITE):
        shutil.copytree(ROOT / relative, tmp_path / relative)
    (tmp_path / "docs").mkdir()
    shutil.copy(ROOT / "docs" / "GOALS.yaml", tmp_path / "docs" / "GOALS.yaml")
    (tmp_path / "plan.yaml").write_text(PLAN, "utf-8")

    def unreachable(*_args: Any, **_kwargs: Any) -> Any:
        raise AssertionError("an offline command called a model")

    monkeypatch.setattr(client, "chat", unreachable)

    chosen = set(
        json.loads((tmp_path / "evals/golden/rag-app-v2/calibracion.json").read_text("utf-8"))["cases"]
    )
    raw = tmp_path / "raw"
    raw.mkdir()
    for spec in matrix.load_plan(tmp_path / "plan.yaml").specs():
        rows = [
            row for row in _rows(tmp_path / SUITE / "sut" / f"{spec.variant}.jsonl") if row["id"] in chosen
        ]
        for row in rows:
            row["verdict"] = "FIEL"
        if spec.run_id == "base-02":
            rows[0]["answer"] = "una respuesta distinta"  # a little noise between two H0 runs
        (raw / f"{spec.run_id}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8"
        )
    return tmp_path


def built(root: Path) -> Path:
    out = root / "fp-matrix.parquet"
    matrix.build(root / "plan.yaml", root, root / "raw", out)
    return out


def test_the_matrix_is_one_value_per_run_case_and_metric_and_says_where_it_came_from(root: Path) -> None:
    metadata, runs = matrix.read_matrix(built(root))

    assert sorted(runs) == ["base-00", "base-01", "base-02", "contexto-50-00", "contexto-50-01"]
    for run in runs.values():
        assert len(run["answer_correct"]) == len(run["faithfulness"]) == 60
        assert len(run["context_recall"]) == 48, "negative cases stay out of the recall denominator"
    assert metadata["baseline"] == "base-00"
    assert metadata["n_cases"] == 60
    assert "sin caché" in metadata["noise_source"]
    assert "RAG_TEMPERATURE=0.7" in metadata["noise_source"]
    assert metadata["runs"]["base-02"] == {
        "variant": "base",
        "seed": 1002,
        "knobs": {"RAG_TEMPERATURE": "0.7", "RAG_SEED": "1002"},
        "raw_sha256": metadata["runs"]["base-02"]["raw_sha256"],
    }
    assert metadata["runs"]["contexto-50-01"]["knobs"]["RAG_CONTEXT_KEEP"] == "0.5"
    assert metadata["judge"]["prompt_sha256"].startswith("sha256:")


def test_a_plan_that_is_not_recorded_whole_is_not_built(root: Path) -> None:
    (root / "raw" / "contexto-50-01.jsonl").unlink()

    with pytest.raises(matrix.MatrixError, match="faltan 1 ejecuciones"):
        built(root)


def test_a_run_cut_short_is_not_a_recorded_run(root: Path) -> None:
    path = root / "raw" / "base-01.jsonl"
    path.write_text("".join(path.read_text("utf-8").splitlines(keepends=True)[:-1]), "utf-8")

    with pytest.raises(matrix.MatrixError, match="base-01"):
        built(root)


def test_a_baseline_that_is_not_a_base_run_is_refused(root: Path) -> None:
    (root / "plan.yaml").write_text(PLAN.replace("baseline: base-00", "baseline: contexto-50-00"), "utf-8")

    with pytest.raises(matrix.MatrixError, match="línea base"):
        built(root)


def test_the_three_goals_are_read_from_the_matrix_and_kept_together(root: Path) -> None:
    path, goals, out = built(root), root / "docs" / "GOALS.yaml", root / "meta-eval.json"
    out.write_text(json.dumps({"cohens_kappa": {"point": 0.47}}), "utf-8")

    meta.fp(path, root, goals, out)
    meta.mde(path, root, goals, out)
    document = meta.sensitivity(path, root, goals, out)

    assert document == json.loads(out.read_text("utf-8"))
    assert document["cohens_kappa"] == {"point": 0.47}, "the other blocks of the document are kept"

    rate = document["fp_rate_baseline_fixed"]
    assert (rate["n"], document["n_decisiones"], rate["baseline"]) == (2, 2, "base-00")
    assert rate["point"] == 0.0, "one changed answer in 60 is noise, and the gate lets it through"
    assert rate["wilson_95"][0] == 0.0 < rate["wilson_95"][1]
    assert document["fuente_de_ruido"] == matrix.read_matrix(path)[0]["noise_source"]
    assert "faithfulness" not in rate["blocking_metrics"], "retired: kappa under its threshold"

    effect = document["mde_pp"]
    assert document["n_casos_subsuite"] == 60
    assert (effect["n_runs"], effect["n_pairs"]) == (3, 6)
    assert effect["point"] == pytest.approx(100 / 60), "one case of sixty, in points"
    assert set(effect["per_metric"]) == set(rate["blocking_metrics"])

    power = document["power"]
    assert list(power["per_degradation"]) == ["contexto-50"]
    cut = power["per_degradation"]["contexto-50"]
    assert (cut["power"], cut["n"], cut["big_enough"]) == (1.0, 2, True)
    assert power["min_over_degradations"] == 1.0
    assert power["mde_pp"] == effect["point"]
    assert power["required_size_pp"] == pytest.approx(1.5 * effect["point"])
    for block in (rate, effect, power):
        assert block["matrix_sha256"].startswith("sha256:")


def test_the_numbers_are_the_same_every_time(root: Path) -> None:
    path, goals = built(root), root / "docs" / "GOALS.yaml"

    first = meta.sensitivity(path, root, goals, root / "a.json")
    second = meta.sensitivity(path, root, goals, root / "b.json")

    assert first == second


def test_a_file_that_is_not_a_matrix_is_refused(root: Path) -> None:
    with pytest.raises(matrix.MatrixError, match="no existe"):
        meta.fp(root / "nada.parquet", root, root / "docs" / "GOALS.yaml", root / "meta-eval.json")


@pytest.mark.parametrize(
    ("document", "source", "n_cases"),
    [("meta-eval.json", "fp-matrix.parquet", 200), ("meta-eval-60.json", "fp-matrix-60.parquet", 60)],
)
def test_the_published_numbers_are_what_the_published_matrix_gives(
    tmp_path: Path, document: str, source: str, n_cases: int
) -> None:
    """Nobody typed them: each matrix in the repository gives its three blocks again, to the last digit.
    Both measurements are published: the one over the 200 cases and the earlier one over 60."""
    published = json.loads((ROOT / "evals" / "reports" / document).read_text("utf-8"))
    path, goals, out = Path("evals/reports") / source, ROOT / "docs" / "GOALS.yaml", tmp_path / "m.json"

    meta.fp(path, ROOT, goals, out)
    meta.mde(path, ROOT, goals, out)
    again = meta.sensitivity(path, ROOT, goals, out)

    for block in (
        "fp_rate_baseline_fixed",
        "mde_pp",
        "power",
        "n_decisiones",
        "n_casos_subsuite",
        "fuente_de_ruido",
    ):
        assert again[block] == published[block], block
    assert published["n_decisiones"] >= 49, "G-GATE-FP asks for at least 49 decisions"
    assert published["n_casos_subsuite"] == n_cases


def test_an_earlier_measurement_is_shown_without_a_kappa_it_does_not_have(root: Path) -> None:
    path, goals = built(root), root / "docs" / "GOALS.yaml"
    document = meta.sensitivity(path, root, goals, root / "m.json")
    meta.fp(path, root, goals, root / "m.json")
    document = meta.mde(path, root, goals, root / "m.json")
    thresholds = yaml.safe_load(goals.read_text("utf-8"))

    table = meta.report_table(document, thresholds, matrix_only=True)

    assert "G-JUDGE-KAPPA" not in table
    assert all(goal in table for goal in ("G-GATE-FP", "G-GATE-MDE", "G-GATE-POWER"))
    with pytest.raises(meta.LabelsError, match="cohens_kappa"):
        meta.report_table(document, thresholds)


def test_a_plan_without_judge_over_the_whole_golden_set(root: Path) -> None:
    """`cases: all` and `judge: off`: 200 cases, no verdicts asked or needed, no judge metric in the matrix,
    and the gate measured is still the suite's own with its blocking metrics."""
    plan = PLAN.replace("cases: evals/golden/rag-app-v2/calibracion.json", 'cases: all\njudge: "off"')
    (root / "plan.yaml").write_text(plan, "utf-8")
    for spec in matrix.load_plan(root / "plan.yaml").specs():
        rows = _rows(root / SUITE / "sut" / f"{spec.variant}.jsonl")
        (root / "raw" / f"{spec.run_id}.jsonl").write_text(
            "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8"
        )

    metadata, runs = matrix.read_matrix(built(root))
    document = meta.sensitivity(
        root / "fp-matrix.parquet", root, root / "docs" / "GOALS.yaml", root / "m.json"
    )

    assert metadata["n_cases"] == 200
    assert metadata["judge"] is None
    assert "sin juez" in metadata["noise_source"]
    assert sorted(runs["base-00"]) == ["abstencion_incorrecta", "answer_correct", "context_recall"]
    assert document["power"]["blocking_metrics"] == [
        "answer_correct",
        "context_recall",
        "abstencion_incorrecta",
    ]
    assert document["power"]["per_degradation"]["contexto-50"]["power"] == 1.0


def test_a_plan_with_a_key_nobody_declared_is_refused(root: Path) -> None:
    (root / "plan.yaml").write_text(PLAN + "temperatura: 0.9\n", "utf-8")
    with pytest.raises(matrix.MatrixError, match="debe declarar"):
        built(root)
    (root / "plan.yaml").write_text(PLAN + "judge: a veces\n", "utf-8")
    with pytest.raises(matrix.MatrixError, match="live u off"):
        built(root)
