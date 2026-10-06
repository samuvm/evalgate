"""G-PRICE-REPRO, held from outside: the suite's report honours the shared eval-report contract, and the suite
is NOT a check that always says zero.

The second half matters more than the first. A reproducibility goal that publishes 0 is only worth something
if it publishes something else when the past is touched, so the corpus is copied and broken on purpose: a
recorded total moved by one cent-thousandth, and a sealed table edited.
"""

import json
import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator, FormatChecker

from evalgate.cli import pricing_repro
from evalgate.pricing.loader import TableError

from ._paths import ROOT

SUITE = ROOT / "evals" / "suites" / "pricing-repro"
SCHEMA = json.loads((ROOT / "docs" / "CONTRACTS" / "eval-report.schema.json").read_text("utf-8"))


@pytest.fixture
def corpus(tmp_path: Path) -> Path:
    return Path(shutil.copytree(SUITE, tmp_path / "pricing-repro"))


def test_the_fixed_corpus_recomputes_to_the_recorded_totals_exactly(corpus: Path, tmp_path: Path) -> None:
    out = tmp_path / "pricing-repro.json"

    worst = pricing_repro.run(corpus, out)

    report = json.loads(out.read_text("utf-8"))
    assert worst == Decimal(0)
    assert list(Draft202012Validator(SCHEMA, format_checker=FormatChecker()).iter_errors(report)) == []
    (metric,) = report["metrics"]
    assert (metric["id"], metric["value"], metric["n"], metric["unit"]) == ("G-PRICE-REPRO", 0.0, 12, "eur")
    cases = json.loads((tmp_path / metric["raw_path"]).read_text("utf-8"))
    assert len(cases) == 12
    assert all(case["match"] for case in cases)


def test_the_corpus_covers_the_five_calculation_rules_of_the_contract(corpus: Path, tmp_path: Path) -> None:
    pricing_repro.run(corpus, tmp_path / "r.json")
    rules = " ".join(case["regla"] for case in json.loads((tmp_path / "r-cases.json").read_text("utf-8")))

    for rule in ("§3.1", "§3.2", "§3.3", "§3.4", "§3.5"):
        assert rule in rules, f"ningún informe del corpus ejercita {rule}"


def test_two_runs_over_the_same_corpus_are_the_same_run(corpus: Path, tmp_path: Path) -> None:
    pricing_repro.run(corpus, tmp_path / "a.json")
    pricing_repro.run(corpus, tmp_path / "b.json")
    first, second = (json.loads((tmp_path / name).read_text("utf-8")) for name in ("a.json", "b.json"))

    assert first["run_id"] == second["run_id"]
    assert first["dataset"] == second["dataset"]
    assert first["metrics"][0]["value"] == second["metrics"][0]["value"]


def test_a_recorded_total_that_no_longer_matches_is_reported_with_its_size(
    corpus: Path, tmp_path: Path
) -> None:
    reports = corpus / "reports.yaml"
    text = reports.read_text("utf-8")
    assert 'recorded_total_eur: "0.585"' in text
    reports.write_text(text.replace('recorded_total_eur: "0.585"', 'recorded_total_eur: "0.58501"'), "utf-8")

    worst = pricing_repro.run(corpus, tmp_path / "r.json")

    assert worst == Decimal("0.00001")
    broken = [c for c in json.loads((tmp_path / "r-cases.json").read_text("utf-8")) if not c["match"]]
    assert [case["id"] for case in broken] == ["R06-volumen-septiembre"]


def test_a_sealed_table_of_the_corpus_that_was_edited_stops_the_suite(corpus: Path, tmp_path: Path) -> None:
    """Not a different number: no number at all. A price changed in the past is not a rounding problem."""
    table = corpus / "tables" / "2026-09-01.yaml"
    table.write_text(
        table.read_text("utf-8").replace("output_per_1k: 0.005", "output_per_1k: 0.004"), "utf-8"
    )

    with pytest.raises(TableError, match=r"2026-09-01\.yaml"):
        pricing_repro.run(corpus, tmp_path / "r.json")
