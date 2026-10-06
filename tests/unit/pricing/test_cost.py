"""The five calculation cases of docs/CONTRACTS/pricing-table.md §3, each with its result worked out BY HAND.

The prices are the contract's own example (§2): per 1k tokens, input 0.0008, output 0.004, cache write 0.001,
cache read 0.00008 USD, at 0.92 USD→EUR. Every expected number below is written as the arithmetic that
produces it, so a reader can check it without running anything.
"""

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from evalgate.pricing.cost import Call, CallCost, Tokens, Unpriced, cost_of, period_total_eur, presented, total_eur
from evalgate.pricing.model import Fx, ModelPrice, PriceTable

HAIKU = ModelPrice(
    input_per_1k=Decimal("0.0008"),
    output_per_1k=Decimal("0.004"),
    cache_write_per_1k=Decimal("0.001"),
    cache_read_per_1k=Decimal("0.00008"),
)
LOCAL = ModelPrice(input_per_1k=Decimal("0"), output_per_1k=Decimal("0"))
AUGUST = PriceTable(
    effective_from=date(2026, 8, 1),
    models={"haiku": HAIKU, "qwen": LOCAL},
    currency="USD",
    fx=Fx(usd_eur=Decimal("0.92"), fx_date=date(2026, 8, 8)),
)
# A price rise on the 1st of September, and the euro moved too.
SEPTEMBER = PriceTable(
    effective_from=date(2026, 9, 1),
    models={"haiku": ModelPrice(input_per_1k=Decimal("0.0010"), output_per_1k=Decimal("0.005"))},
    currency="USD",
    fx=Fx(usd_eur=Decimal("0.90"), fx_date=date(2026, 9, 1)),
)
MID_AUGUST = datetime(2026, 8, 15, 12, tzinfo=UTC)


def test_case_1_input_and_output_are_priced_apart() -> None:
    cost = cost_of([AUGUST], "haiku", Tokens(input=1500, output=500), MID_AUGUST)

    # 1.5 × 0.0008 + 0.5 × 0.004 = 0.0012 + 0.0020 = 0.0032 USD;  × 0.92 = 0.002944 EUR
    assert cost == CallCost(Decimal("0.0032"), "USD", Decimal("0.002944"), "2026-08-01")


def test_case_2_a_period_that_crosses_a_price_change_uses_each_table_for_its_stretch() -> None:
    tables = [AUGUST, SEPTEMBER]
    last_second_of_august = datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC)
    first_instant_of_september = datetime(2026, 9, 1, tzinfo=UTC)
    same = Tokens(input=1000, output=1000)

    before = cost_of(tables, "haiku", same, last_second_of_august)
    after = cost_of(tables, "haiku", same, first_instant_of_september)

    assert before is not None
    assert after is not None
    # August: 0.0008 + 0.004 = 0.0048 USD × 0.92 = 0.004416 EUR
    assert (before.eur, before.pricing_version) == (Decimal("0.004416"), "2026-08-01")
    # September: 0.0010 + 0.005 = 0.0060 USD × 0.90 = 0.005400 EUR
    assert (after.eur, after.pricing_version) == (Decimal("0.0054"), "2026-09-01")
    assert total_eur([before, after]) == Decimal("0.009816")


def test_case_3_prompt_cache_write_and_read_have_their_own_prices() -> None:
    cost = cost_of([AUGUST], "haiku", Tokens(1000, 0, cache_write=2000, cache_read=10_000), MID_AUGUST)

    # 1 × 0.0008 + 2 × 0.001 + 10 × 0.00008 = 0.0008 + 0.0020 + 0.0008 = 0.0036 USD
    assert cost is not None
    assert cost.amount == Decimal("0.0036")


def test_case_3_cache_tokens_on_a_model_with_no_cache_price_are_an_error_not_free() -> None:
    """Pricing them at zero would publish a cost lower than the bill and call it exact."""
    with pytest.raises(ValueError, match="cache"):
        cost_of([SEPTEMBER], "haiku", Tokens(1000, 0, cache_read=10), datetime(2026, 9, 2, tzinfo=UTC))


def test_case_4_the_tokens_of_a_hung_up_stream_cost_what_any_tokens_cost() -> None:
    """The function does not know, and must not know, whether the client stayed to read them (R2)."""
    emitted_before_the_hang_up = Tokens(input=15, output=2)

    cost = cost_of([AUGUST], "haiku", emitted_before_the_hang_up, MID_AUGUST)

    # 0.015 × 0.0008 + 0.002 × 0.004 = 0.000012 + 0.000008 = 0.00002 USD
    assert cost is not None
    assert cost.amount == Decimal("0.00002")


def test_case_5_rounding_happens_once_when_presenting_never_per_call() -> None:
    call = CallCost(Decimal("0.004"), "EUR", Decimal("0.004"), "2026-08-01")

    exact = total_eur([call, call, call])

    assert exact == Decimal("0.012")
    assert presented(exact) == Decimal("0.01")
    # Rounding each call first loses the whole amount: 0.00 + 0.00 + 0.00.
    assert sum(presented(c.eur) for c in (call, call, call)) == Decimal("0.00")


@pytest.mark.parametrize(
    ("amount", "places", "shown"),
    [("0.005", 2, "0.01"), ("0.0049", 2, "0.00"), ("2.345", 2, "2.35"), ("0.002944", 4, "0.0029")],
)
def test_presented_rounds_half_up_to_the_places_asked(amount: str, places: int, shown: str) -> None:
    assert presented(Decimal(amount), places) == Decimal(shown)
    assert presented(Decimal(amount), places).as_tuple().exponent == -places


def test_a_local_model_costs_zero_and_that_is_a_price_not_an_absence() -> None:
    """Contract §4: the real cost incurred locally is 0 €. `None` would mean "nobody knows"."""
    cost = cost_of([AUGUST], "qwen", Tokens(input=10_000, output=5_000), MID_AUGUST)

    assert cost == CallCost(Decimal("0"), "USD", Decimal("0"), "2026-08-01")


def test_a_model_the_table_does_not_list_has_no_cost_rather_than_a_free_one() -> None:
    assert cost_of([AUGUST], "gpt-nobody-priced", Tokens(1000, 1000), MID_AUGUST) is None


def test_a_call_before_the_first_table_has_no_cost() -> None:
    assert cost_of([AUGUST], "haiku", Tokens(1000, 1000), datetime(2026, 7, 31, tzinfo=UTC)) is None


def test_a_table_in_euros_needs_no_exchange_rate_and_applies_none() -> None:
    euros = PriceTable(date(2026, 8, 1), {"haiku": HAIKU}, currency="EUR")

    cost = cost_of([euros], "haiku", Tokens(input=1500, output=500), MID_AUGUST)

    assert cost == CallCost(Decimal("0.0032"), "EUR", Decimal("0.0032"), "2026-08-01")


def test_a_dollar_table_without_its_exchange_rate_is_refused() -> None:
    """R3: an assumed rate would be a price living in the code."""
    no_fx = PriceTable(date(2026, 8, 1), {"haiku": HAIKU}, currency="USD")

    with pytest.raises(ValueError, match="fx"):
        cost_of([no_fx], "haiku", Tokens(1, 1), MID_AUGUST)


def test_a_table_that_does_not_say_its_currency_is_refused() -> None:
    with pytest.raises(ValueError, match="currency"):
        cost_of([PriceTable(date(2026, 8, 1), {"haiku": HAIKU})], "haiku", Tokens(1, 1), MID_AUGUST)


@pytest.mark.parametrize("tokens", [Tokens(-1, 0), Tokens(0, -1), Tokens(0, 0, cache_write=-1), Tokens(0, 0, 0, -1)])
def test_negative_tokens_are_corrupt_input(tokens: Tokens) -> None:
    with pytest.raises(ValueError, match="negative"):
        cost_of([AUGUST], "haiku", tokens, MID_AUGUST)


def test_total_of_nothing_is_zero() -> None:
    assert total_eur([]) == Decimal("0")


# --- a whole period: each call with the table of ITS date (contract §3.2) -------------------------------


def test_a_period_across_a_price_change_prices_each_call_with_its_own_table() -> None:
    same = Tokens(input=1000, output=1000)
    calls = [
        Call(datetime(2026, 8, 31, 23, 59, 59, tzinfo=UTC), "haiku", same),  # 0.0048 USD x 0.92 = 0.004416
        Call(datetime(2026, 9, 1, tzinfo=UTC), "haiku", same),  # 0.0060 USD x 0.90 = 0.005400
        Call(datetime(2026, 8, 20, tzinfo=UTC), "qwen", Tokens(50_000, 50_000)),  # local: 0
    ]

    assert period_total_eur([AUGUST, SEPTEMBER], calls) == Decimal("0.009816")


def test_a_period_with_one_call_nobody_can_price_has_no_total() -> None:
    """September's table does not list qwen. Skipping the call would publish a total that looks complete."""
    calls = [
        Call(MID_AUGUST, "haiku", Tokens(1000, 0)),
        Call(datetime(2026, 9, 2, tzinfo=UTC), "qwen", Tokens(1000, 0)),
    ]

    with pytest.raises(Unpriced, match="qwen"):
        period_total_eur([AUGUST, SEPTEMBER], calls)


def test_an_empty_period_costs_zero() -> None:
    assert period_total_eur([AUGUST], []) == Decimal("0")
