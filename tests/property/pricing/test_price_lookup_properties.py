"""Properties of price_at (RULES §4.2: every public function of pricing/ needs a property test)."""

import random
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from evalgate.pricing.lookup import price_at
from evalgate.pricing.model import ModelPrice, PriceComponent, PriceTable

DAYS = st.dates(min_value=date(2020, 1, 1), max_value=date(2030, 12, 31))
PRICES = st.integers(min_value=0, max_value=10**6).map(lambda n: Decimal(n) / Decimal(10**6))
INSTANTS = st.datetimes(
    min_value=datetime(2020, 1, 1), max_value=datetime(2030, 12, 31), timezones=st.just(UTC)
)


@st.composite
def tables(draw: st.DrawFn) -> list[PriceTable]:
    days = draw(st.lists(DAYS, min_size=1, max_size=6, unique=True))
    return [
        PriceTable(effective_from=d, models={"m": ModelPrice(draw(PRICES), draw(PRICES))}) for d in days
    ]


@given(tables(), INSTANTS, st.randoms(use_true_random=False))
def test_resolution_does_not_depend_on_table_order(
    history: list[PriceTable], at: datetime, rnd: random.Random
) -> None:
    shuffled = history[:]
    rnd.shuffle(shuffled)

    assert price_at(shuffled, "m", PriceComponent.INPUT, at) == price_at(
        history, "m", PriceComponent.INPUT, at
    )


@given(tables(), INSTANTS, st.integers(min_value=1, max_value=400), PRICES)
def test_a_table_published_after_the_instant_never_applies(
    history: list[PriceTable], at: datetime, days_later: int, price: Decimal
) -> None:
    future_day = at.date() + timedelta(days=days_later)
    if any(t.effective_from == future_day for t in history):
        return
    future = PriceTable(effective_from=future_day, models={"m": ModelPrice(price, price)})

    assert price_at([*history, future], "m", PriceComponent.INPUT, at) == price_at(
        history, "m", PriceComponent.INPUT, at
    )


@given(tables(), INSTANTS)
def test_the_price_comes_from_the_latest_table_in_force(history: list[PriceTable], at: datetime) -> None:
    in_force = [t for t in history if t.effective_from <= at.date()]
    result = price_at(history, "m", PriceComponent.INPUT, at)

    if not in_force:
        assert result is None
    else:
        assert result == max(in_force, key=lambda t: t.effective_from).models["m"].input_per_1k


@given(tables(), INSTANTS)
def test_price_is_never_negative(history: list[PriceTable], at: datetime) -> None:
    for component in (PriceComponent.INPUT, PriceComponent.OUTPUT):
        result = price_at(history, "m", component, at)
        assert result is None or result >= 0
