"""F0 contract level: every schema the project depends on is valid JSON Schema 2020-12, and the
documents that must conform to them do."""

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator

from ._paths import ROOT

DRAFT_2020_12 = "https://json-schema.org/draft/2020-12/schema"
SCHEMAS = [
    "docs/CONTRACTS/eval-report.schema.json",
    "docs/CONTRACTS/goals.schema.json",
    "docs/spec/pricing-table.schema.json",
]


def _json(path: str) -> Any:
    return json.loads((ROOT / path).read_text(encoding="utf-8"))


def _yaml_as_json(text: str) -> Any:
    """YAML loads dates as datetime.date; JSON Schema sees documents as JSON, so dates become ISO strings."""
    return json.loads(json.dumps(yaml.safe_load(text), default=str))


@pytest.mark.parametrize("path", SCHEMAS)
def test_schema_is_valid_draft_2020_12(path: str) -> None:
    schema = _json(path)

    assert schema["$schema"] == DRAFT_2020_12
    Draft202012Validator.check_schema(schema)


def test_goals_yaml_conforms_to_shared_contract() -> None:
    goals = _yaml_as_json((ROOT / "docs/GOALS.yaml").read_text(encoding="utf-8"))

    Draft202012Validator(_json("docs/CONTRACTS/goals.schema.json")).validate(goals)


def test_goal_ids_are_unique() -> None:
    goals = _yaml_as_json((ROOT / "docs/GOALS.yaml").read_text(encoding="utf-8"))
    ids = [meta["id"] for meta in goals["metas"]]

    assert len(ids) == len(set(ids))


def test_pricing_contract_example_conforms_to_own_spec() -> None:
    contract = (ROOT / "docs/CONTRACTS/pricing-table.md").read_text(encoding="utf-8")
    example = re.search(r"```yaml\n(.*?)```", contract, re.DOTALL)
    assert example is not None, "pricing-table.md §2 has no yaml example"

    Draft202012Validator(_json("docs/spec/pricing-table.schema.json")).validate(_yaml_as_json(example[1]))


def test_hash_exclusions_point_at_report_fields() -> None:
    exclusions = yaml.safe_load((ROOT / "evals/report-hash-exclusions.yaml").read_text(encoding="utf-8"))
    report_fields = _json("docs/CONTRACTS/eval-report.schema.json")["properties"]

    assert exclusions["exclusions"]
    for entry in exclusions["exclusions"]:
        assert entry["path"].startswith("$.")
        assert entry["motivo"].strip()
        assert entry["path"].split(".")[1] in report_fields


def test_run_id_is_never_excluded_from_the_report_hash() -> None:
    exclusions = yaml.safe_load((ROOT / "evals/report-hash-exclusions.yaml").read_text(encoding="utf-8"))

    assert "$.run_id" not in {entry["path"] for entry in exclusions["exclusions"]}


def test_schema_paths_exist() -> None:
    for path in SCHEMAS:
        assert Path(ROOT / path).is_file()
