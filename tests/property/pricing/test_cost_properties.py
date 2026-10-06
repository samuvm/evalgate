"""The three properties docs/CONTRACTS/pricing-table.md §3 asks for, plus rounding (RULES §4.2 point 2).

1. The cost is never negative.
2. Adding tokens never reduces the cost.
3. The cost of a batch is the sum of its parts: exactly, to the last digit, because nothing is rounded
   before presenting (§3.5). A float anywhere in the path would break this one.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

from hypothesis import given
from hypothesis import strategies as st

from evalgate.pricing.cost import CallCost, Tokens, cost_of, presented, total_eur
from evalgate.pricing.model import Fx, ModelPrice, PriceTable

PRICES = st.integers(min_value=0, max_value=10**6).map(lambda n: Decimal(n) / Decimal(10**6))
RATES = st.integers(min_value=1, max_value=2 * 10**4).map(lambda n: Decimal(n) / Decimal(10**4))
COUNTS = st.integers(min_value=0, max_value=10**7)
TOKENS = st.builds(Tokens, input=COUNTS, output=COUNTS, cache_write=COUNTS, cache_read=COUNTS)
AT = datetime(2026, 8, 15, tzinfo=UTC)


@st.composite
def tables(draw: st.DrawFn) -> list[PriceTable]:
    price = ModelPrice(draw(PRICES), draw(PRICES), draw(PRICES), draw(PRICES))
    return [PriceTable(date(2026, 8, 1), {"m": price}, "USD", Fx(draw(RATES), date(2026, 8, 1)))]


def plus(a: Tokens, b: Tokens) -> Tokens:
    return Tokens(a.input + b.input, a.output + b.output, a.cache_write + b.cache_write, a.cache_read + b.cache_read)


def priced(history: list[PriceTable], tokens: Tokens) -> CallCost:
    cost = cost_of(history, "m", tokens, AT)
    assert cost is not None
    return cost


@given(tables(), TOKENS)
def test_cost_is_never_negative(history: list[PriceTable], tokens: Tokens) -> None:
    cost = priced(history, tokens)

    assert cost.amount >= 0
    assert cost.eur >= 0


@given(tables(), TOKENS, TOKENS)
def test_adding_tokens_never_reduces_the_cost(history: list[PriceTable], base: Tokens, more: Tokens) -> None:
    assert priced(history, plus(base, more)).eur >= priced(history, base).eur


@given(tables(), st.lists(TOKENS, max_size=8))
def test_the_cost_of_a_batch_is_exactly_the_sum_of_its_parts(history: list[PriceTable], batch: list[Tokens]) -> None:
    whole = Tokens(0, 0)
    for part in batch:
        whole = plus(whole, part)

    assert total_eur(priced(history, part) for part in batch) == priced(history, whole).eur


@given(st.decimals(min_value=0, max_value=10**9, places=9), st.integers(min_value=0, max_value=6))
def test_presenting_moves_an_amount_by_at_most_half_a_unit(amount: Decimal, places: int) -> None:
    unit = Decimal(1).scaleb(-places)

    assert abs(presented(amount, places) - amount) <= unit / 2
