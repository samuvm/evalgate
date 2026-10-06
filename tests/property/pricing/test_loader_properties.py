"""Properties of the loader (RULES §4.2 point 2: every public function of pricing/ has one).

- `parse_table`: whatever prices a table is written with, it loads with exactly those digits.
- `load_tables`: changing ANY single byte of a sealed table makes the whole history unloadable (R4).
"""

import hashlib
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from evalgate.pricing.loader import TableError, load_tables, parse_table

PRICES = st.integers(min_value=0, max_value=10**9).map(lambda n: Decimal(n).scaleb(-8))
DAYS = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
MODEL_IDS = st.from_regex(r"[a-z][a-z0-9.:-]{0,20}", fullmatch=True)


def written(day: date, prices: dict[str, tuple[Decimal, Decimal]]) -> str:
    models = "".join(
        f"  - id: \"{model}\"\n    provider: p\n    region: r\n    input_per_1k: {i:f}\n    output_per_1k: {o:f}\n"
        for model, (i, o) in prices.items()
    )
    return (
        f"effective_from: {day.isoformat()}\nsource: https://example.com/pricing\nretrieved_at: {day.isoformat()}\n"
        f"currency: EUR\nfx:\n  USD_EUR: 0.9\n  fx_date: {day.isoformat()}\nmodels:\n{models}"
    )


@given(DAYS, st.dictionaries(MODEL_IDS, st.tuples(PRICES, PRICES), min_size=1, max_size=5))
def test_a_table_loads_with_exactly_the_digits_it_was_written_with(
    day: date, prices: dict[str, tuple[Decimal, Decimal]]
) -> None:
    table = parse_table(written(day, prices), f"{day.isoformat()}.yaml")

    assert table is not None
    assert table.effective_from == day
    assert {m: (p.input_per_1k, p.output_per_1k) for m, p in table.models.items()} == prices


@given(DAYS, PRICES, PRICES, st.data())
def test_any_single_byte_changed_in_a_sealed_table_makes_it_unloadable(
    day: date, price_in: Decimal, price_out: Decimal, data: st.DataObject
) -> None:
    text = written(day, {"m": (price_in, price_out)}).encode()
    position = data.draw(st.integers(min_value=0, max_value=len(text) - 1))
    flipped = text[:position] + bytes([text[position] ^ 1]) + text[position + 1 :]
    with tempfile.TemporaryDirectory() as tmp:
        directory, lock = Path(tmp), Path(tmp) / "TABLES.lock"
        name = f"{day.isoformat()}.yaml"
        (directory / name).write_bytes(text)
        lock.write_text(f"{hashlib.sha256(text).hexdigest()}  pricing/{name}\n", encoding="utf-8")
        assert [t.effective_from for t in load_tables(directory, lock)] == [day]

        (directory / name).write_bytes(flipped)
        with pytest.raises(TableError):
            load_tables(directory, lock)
