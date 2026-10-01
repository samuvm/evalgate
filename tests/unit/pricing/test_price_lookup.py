from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from evalgate.pricing.lookup import price_at
from evalgate.pricing.model import ModelPrice, PriceComponent, PriceTable


def _table(effective_from: date, input_per_1k: str) -> PriceTable:
    return PriceTable(
        effective_from=effective_from,
        models={"m": ModelPrice(input_per_1k=Decimal(input_per_1k), output_per_1k=Decimal("0.004"))},
    )


def test_price_at_valid_from_boundary() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008"), _table(date(2026, 9, 1), "0.0010")]
    boundary = datetime(2026, 9, 1, tzinfo=UTC)

    assert price_at(tables, "m", PriceComponent.INPUT, boundary) == Decimal("0.0010")


def test_price_at_one_microsecond_before_boundary_uses_previous_table() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008"), _table(date(2026, 9, 1), "0.0010")]
    just_before = datetime(2026, 8, 31, 23, 59, 59, 999999, tzinfo=UTC)

    assert price_at(tables, "m", PriceComponent.INPUT, just_before) == Decimal("0.0008")


def test_price_at_before_first_table_is_none() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008")]

    assert price_at(tables, "m", PriceComponent.INPUT, datetime(2026, 7, 31, tzinfo=UTC)) is None


def test_price_at_unknown_model_is_none() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008")]

    assert price_at(tables, "other", PriceComponent.INPUT, datetime(2026, 8, 2, tzinfo=UTC)) is None


def test_model_missing_from_table_in_force_does_not_fall_back_to_older_table() -> None:
    older = _table(date(2026, 8, 1), "0.0008")
    newer = PriceTable(effective_from=date(2026, 9, 1), models={})

    assert price_at([older, newer], "m", PriceComponent.INPUT, datetime(2026, 9, 2, tzinfo=UTC)) is None


def test_price_at_returns_each_component_from_its_own_field() -> None:
    price = ModelPrice(
        input_per_1k=Decimal("1"),
        output_per_1k=Decimal("2"),
        cache_write_per_1k=Decimal("3"),
        cache_read_per_1k=Decimal("4"),
    )
    tables = [PriceTable(effective_from=date(2026, 8, 1), models={"m": price})]
    at = datetime(2026, 8, 2, tzinfo=UTC)

    assert [price_at(tables, "m", c, at) for c in PriceComponent] == [Decimal(n) for n in "1234"]


def test_unpriced_cache_component_is_none() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008")]

    assert price_at(tables, "m", PriceComponent.CACHE_READ, datetime(2026, 8, 2, tzinfo=UTC)) is None


def test_price_at_rejects_duplicate_effective_from() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008"), _table(date(2026, 8, 1), "0.0009")]

    with pytest.raises(ValueError, match="effective_from"):
        price_at(tables, "m", PriceComponent.INPUT, datetime(2026, 8, 2, tzinfo=UTC))


def test_price_at_rejects_naive_datetime() -> None:
    tables = [_table(date(2026, 8, 1), "0.0008")]

    with pytest.raises(ValueError, match="timezone"):
        price_at(tables, "m", PriceComponent.INPUT, datetime(2026, 8, 2))  # noqa: DTZ001 - the case under test
