"""The loader validates by hand (`jsonschema` is a dev dependency), so this is what keeps it honest: the same
documents go through `docs/spec/pricing-table.schema.json` and through `parse_table`, and the two must agree
on every one. A loader more lenient than the schema would accept a table the contract forbids; a stricter one
is allowed only where the schema itself says the loader adds a rule, and those cases are named.
"""

import json
from typing import Any

import pytest
import yaml
from jsonschema import Draft202012Validator, FormatChecker

from evalgate.pricing.loader import TableError, parse_table

from ._paths import ROOT

SCHEMA = json.loads((ROOT / "docs" / "spec" / "pricing-table.schema.json").read_text("utf-8"))
VALID = """\
effective_from: 2026-08-01
source: https://aws.amazon.com/bedrock/pricing/
retrieved_at: 2026-08-08
currency: USD
fx:
  USD_EUR: 0.92
  fx_date: 2026-08-08
models:
  - id: anthropic.claude-haiku-4-5
    provider: aws.bedrock
    region: eu-west-1
    input_per_1k: 0.0008
    output_per_1k: 0.004
    cache_write_per_1k: 0.001
    cache_read_per_1k: 0.00008
  - id: qwen3.5:9b-mlx
    provider: ollama
    region: local
    input_per_1k: 0.0
    output_per_1k: 0.0
    note: "Coste real incurrido = 0."
"""
EDITS = {
    "sin currency": ("currency: USD\n", ""),
    "sin source": ("source: https://aws.amazon.com/bedrock/pricing/\n", ""),
    "sin fx_date": ("  fx_date: 2026-08-08\n", ""),
    "moneda fuera del enum": ("currency: USD", "currency: GBP"),
    "campo extra en la raíz": ("currency: USD", "currency: USD\ndiscount: 0.5"),
    "campo extra en un modelo": ("    region: local\n", "    region: local\n    price: 3\n"),
    "modelo sin region": ("    region: eu-west-1\n", ""),
    "precio negativo": ("input_per_1k: 0.0008", "input_per_1k: -0.0008"),
    "precio que no es número": ("output_per_1k: 0.004", "output_per_1k: caro"),
    "tipo de cambio cero": ("USD_EUR: 0.92", "USD_EUR: 0"),
    "fecha que no es fecha": ("effective_from: 2026-08-01", "effective_from: agosto"),
}


def by_schema(text: str) -> list[str]:
    """Schema errors, loading the YAML the way the schema's description says: dates as ISO strings."""
    document: Any = yaml.safe_load(text)

    def iso(node: Any) -> Any:
        if isinstance(node, dict):
            return {key: iso(value) for key, value in node.items()}
        if isinstance(node, list):
            return [iso(item) for item in node]
        return node.isoformat() if hasattr(node, "isoformat") else node

    validator = Draft202012Validator(SCHEMA, format_checker=FormatChecker())
    return [error.message for error in validator.iter_errors(iso(document))]


def by_loader(text: str) -> str | None:
    try:
        parse_table(text, "2026-08-01.yaml")
    except TableError as refused:
        return str(refused)
    return None


def test_schema_and_loader_both_accept_the_contract_example() -> None:
    assert by_schema(VALID) == []
    assert by_loader(VALID) is None


@pytest.mark.parametrize("case", sorted(EDITS))
def test_schema_and_loader_refuse_the_same_documents(case: str) -> None:
    old, new = EDITS[case]
    assert old in VALID
    text = VALID.replace(old, new)

    assert by_schema(text), f"el esquema acepta: {case}"
    assert by_loader(text) is not None, f"el cargador acepta: {case}"


def test_the_rules_the_schema_leaves_to_the_loader_are_only_the_ones_it_names() -> None:
    """Schema description: (1) file name = effective_from, (2) no duplicated model. The schema accepts both
    documents; the loader refuses them. (3), the digest in TABLES.lock, is `load_tables`, tested apart."""
    twice = VALID + VALID[VALID.index("  - id: qwen") :]

    assert by_schema(twice) == []
    assert by_loader(twice) is not None
    with pytest.raises(TableError):
        parse_table(VALID, "2026-08-02.yaml")
