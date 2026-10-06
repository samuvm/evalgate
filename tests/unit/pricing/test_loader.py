"""A price table file becomes a `PriceTable` only if it is exactly what the contract describes AND exactly what
was published. Everything else is refused with the reason: a cost computed from a table nobody can vouch for
is worse than no cost.
"""

import hashlib
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from evalgate.pricing.loader import TableError, load_tables, parse_table
from evalgate.pricing.model import Fx, ModelPrice

# The example of docs/CONTRACTS/pricing-table.md §2, as it is written there.
CONTRACT_EXAMPLE = """\
effective_from: 2026-08-01
source: https://aws.amazon.com/bedrock/pricing/   # URL consultada
retrieved_at: 2026-08-08
currency: USD
fx:
  USD_EUR: 0.92          # tipo usado, con su fecha
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
    note: "Coste real incurrido = 0. Ver §4."
"""


def edited(old: str, new: str) -> str:
    assert old in CONTRACT_EXAMPLE
    return CONTRACT_EXAMPLE.replace(old, new)


def test_the_example_of_the_contract_loads_as_written() -> None:
    table = parse_table(CONTRACT_EXAMPLE, "2026-08-01.yaml")

    assert table is not None
    assert (table.effective_from, table.currency) == (date(2026, 8, 1), "USD")
    assert table.fx == Fx(usd_eur=Decimal("0.92"), fx_date=date(2026, 8, 8))
    assert table.models["anthropic.claude-haiku-4-5"] == ModelPrice(
        Decimal("0.0008"), Decimal("0.004"), Decimal("0.001"), Decimal("0.00008"), "aws.bedrock", "eu-west-1"
    )
    assert table.models["qwen3.5:9b-mlx"] == ModelPrice(Decimal("0.0"), Decimal("0.0"), None, None, "ollama", "local")


def test_a_price_is_the_digits_written_in_the_file_not_their_float() -> None:
    """0.1 + 0.2 is not 0.3 in floats. A price read through one stops being the published price."""
    table = parse_table(edited("input_per_1k: 0.0008", "input_per_1k: 0.1"), "2026-08-01.yaml")

    assert table is not None
    price = table.models["anthropic.claude-haiku-4-5"].input_per_1k
    assert price + price + price == Decimal("0.3")
    assert str(price) == "0.1"


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        (edited("currency: USD\n", ""), "currency"),
        (edited("retrieved_at: 2026-08-08\n", ""), "retrieved_at"),
        (edited("  fx_date: 2026-08-08\n", ""), "fx_date"),
        (edited("currency: USD", "currency: GBP"), "currency"),
        (edited("currency: USD", "currency: USD\ndiscount: 0.5"), "discount"),
        (edited("    region: eu-west-1\n", ""), "region"),
        (edited("    region: local\n", "    region: local\n    price: 3\n"), "price"),
        (edited("input_per_1k: 0.0008", "input_per_1k: -0.0008"), "input_per_1k"),
        (edited("input_per_1k: 0.0008", "input_per_1k: barato"), "input_per_1k"),
        (edited("USD_EUR: 0.92 ", "USD_EUR: 0    "), "USD_EUR"),
        (edited("effective_from: 2026-08-01", "effective_from: agosto"), "effective_from"),
        (edited("source: https://aws.amazon.com/bedrock/pricing/", "source: me lo dijeron"), "source"),
        (edited("    provider: ollama\n", "    provider: \"\"\n"), "provider"),
        ("- solo\n- una lista\n", "mapping"),
        ("effective_from: [2026\n", "YAML"),
    ],
)
def test_a_table_that_departs_from_the_contract_is_refused_with_its_reason(text: str, reason: str) -> None:
    with pytest.raises(TableError, match=reason):
        parse_table(text, "2026-08-01.yaml")


def test_a_table_without_models_prices_nothing_and_is_refused() -> None:
    text = CONTRACT_EXAMPLE[: CONTRACT_EXAMPLE.index("models:")] + "models: []\n"

    with pytest.raises(TableError, match="models"):
        parse_table(text, "2026-08-01.yaml")


def test_the_file_name_is_the_effective_date_or_the_table_is_refused() -> None:
    """Schema rule 1: a table named for one day and effective another would be resolved by the wrong one."""
    with pytest.raises(TableError, match="2026-08-02.yaml"):
        parse_table(CONTRACT_EXAMPLE, "2026-08-02.yaml")


def test_the_same_model_twice_is_refused() -> None:
    twice = CONTRACT_EXAMPLE + CONTRACT_EXAMPLE[CONTRACT_EXAMPLE.index("  - id: qwen") :]

    with pytest.raises(TableError, match="qwen3.5:9b-mlx"):
        parse_table(twice, "2026-08-01.yaml")


def test_the_same_model_id_under_two_regions_is_refused_until_the_lookup_can_tell_them_apart() -> None:
    """The schema allows it; `price_at` looks a model up by id alone and would silently pick one. ADR-013."""
    other_region = CONTRACT_EXAMPLE + (
        "\n  - id: qwen3.5:9b-mlx\n    provider: ollama\n    region: otra\n"
        "    input_per_1k: 0.1\n    output_per_1k: 0.1\n"
    )

    with pytest.raises(TableError, match="qwen3.5:9b-mlx"):
        parse_table(other_region, "2026-08-01.yaml")


# --- load_tables: only what was published, exactly as it was published (R4) -----------------------------


def publish(directory: Path, name: str, text: str) -> None:
    (directory / name).write_text(text, encoding="utf-8")


def seal(directory: Path, lock: Path) -> None:
    lines = [
        f"{hashlib.sha256(p.read_bytes()).hexdigest()}  pricing/{p.name}\n" for p in sorted(directory.glob("*.yaml"))
    ]
    lock.write_text("".join(lines), encoding="utf-8")


SEPTEMBER = edited("effective_from: 2026-08-01", "effective_from: 2026-09-01")


def test_sealed_tables_load_in_date_order(tmp_path: Path) -> None:
    publish(tmp_path, "2026-09-01.yaml", SEPTEMBER)
    publish(tmp_path, "2026-08-01.yaml", CONTRACT_EXAMPLE)
    seal(tmp_path, tmp_path / "TABLES.lock")

    tables = load_tables(tmp_path, tmp_path / "TABLES.lock")

    assert [t.effective_from for t in tables] == [date(2026, 8, 1), date(2026, 9, 1)]


def test_a_table_edited_after_being_sealed_is_refused(tmp_path: Path) -> None:
    publish(tmp_path, "2026-08-01.yaml", CONTRACT_EXAMPLE)
    seal(tmp_path, tmp_path / "TABLES.lock")
    publish(tmp_path, "2026-08-01.yaml", edited("output_per_1k: 0.004", "output_per_1k: 0.003"))

    with pytest.raises(TableError, match="2026-08-01.yaml"):
        load_tables(tmp_path, tmp_path / "TABLES.lock")


def test_a_table_nobody_sealed_is_not_published_and_is_refused(tmp_path: Path) -> None:
    publish(tmp_path, "2026-08-01.yaml", CONTRACT_EXAMPLE)
    seal(tmp_path, tmp_path / "TABLES.lock")
    publish(tmp_path, "2026-09-01.yaml", SEPTEMBER)

    with pytest.raises(TableError, match="2026-09-01.yaml"):
        load_tables(tmp_path, tmp_path / "TABLES.lock")


def test_a_sealed_table_that_went_missing_is_refused(tmp_path: Path) -> None:
    """Deleting the past changes every report that was priced with it, as surely as editing it."""
    publish(tmp_path, "2026-08-01.yaml", CONTRACT_EXAMPLE)
    publish(tmp_path, "2026-09-01.yaml", SEPTEMBER)
    seal(tmp_path, tmp_path / "TABLES.lock")
    (tmp_path / "2026-08-01.yaml").unlink()

    with pytest.raises(TableError, match="2026-08-01.yaml"):
        load_tables(tmp_path, tmp_path / "TABLES.lock")


def test_no_tables_and_no_lock_is_an_empty_history_not_an_error(tmp_path: Path) -> None:
    assert load_tables(tmp_path, tmp_path / "TABLES.lock") == []


def test_tables_without_any_lock_are_refused(tmp_path: Path) -> None:
    publish(tmp_path, "2026-08-01.yaml", CONTRACT_EXAMPLE)

    with pytest.raises(TableError, match="TABLES.lock"):
        load_tables(tmp_path, tmp_path / "TABLES.lock")
