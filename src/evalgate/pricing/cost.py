"""Cost of a call with the price table in force AT ITS DATE (docs/CONTRACTS/pricing-table.md §3).

Three rules hold everything else up:

- **Exact until presented.** Amounts are `Decimal` and nothing is rounded here: the contract (§3.5) wants the
  rounding once, when a number is shown, because rounding per call loses money that adds up (three calls of
  0.004 € are 0.01 €, not 0.00 €). `presented` is the only place that rounds.
- **The table of THEN, never of now.** The price comes from `price_at`, which resolves the table by the
  instant of the call. A report of three months ago recomputes to the same cent (G-PRICE-REPRO).
- **No price lives here** (R3). No default rate, no default currency, no fallback price: a table that does not
  say something is refused, because an assumed number would be a price written in the code.

"Free" and "unknown" are different answers: a local model priced at 0 costs `0`; a model no table lists costs
`None`, and nobody downstream may read that as zero.
"""

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, time
from decimal import ROUND_HALF_UP, Decimal

from evalgate.pricing.lookup import price_at
from evalgate.pricing.model import PriceComponent, PriceTable

_PER = 1000  # prices are per 1k tokens: a unit of the contract's format, not a price


@dataclass(frozen=True, slots=True)
class Tokens:
    """Billable tokens of one call, by class. Cache write and cache read are priced apart (contract §3.3)."""

    input: int
    output: int
    cache_write: int = 0
    cache_read: int = 0


@dataclass(frozen=True, slots=True)
class CallCost:
    amount: Decimal  # exact, in the table's currency: never rounded here (contract §3.5)
    currency: str
    eur: Decimal  # exact
    pricing_version: str  # `effective_from` of the table that priced it, ISO date


@dataclass(frozen=True, slots=True)
class Call:
    """One billed call of a period: when, which model, how many tokens."""

    at: datetime
    model_id: str
    tokens: Tokens


class Unpriced(ValueError):
    """A period holds a call no table prices. Its total does not exist, and zero would be a lie."""


def _in_force(tables: Sequence[PriceTable], at: datetime) -> PriceTable | None:
    started = [t for t in tables if datetime.combine(t.effective_from, time.min, UTC) <= at]
    return max(started, key=lambda t: t.effective_from) if started else None


def _to_eur(amount: Decimal, table: PriceTable) -> Decimal:
    if table.currency == "EUR":
        return amount
    if table.currency != "USD":
        raise ValueError(
            f"price table {table.effective_from}: currency must be USD or EUR, not {table.currency!r}"
        )
    if table.fx is None:
        raise ValueError(f"price table {table.effective_from}: USD prices need their fx (rate and date)")
    return amount * table.fx.usd_eur


def cost_of(tables: Sequence[PriceTable], model_id: str, tokens: Tokens, at: datetime) -> CallCost | None:
    """What `tokens` of `model_id` cost at instant `at`. `None` when no table in force prices that model.

    Raises ValueError for corrupt input: negative tokens, cache tokens on a model with no cache price (pricing
    them at zero would publish a cost below the bill), a naive `at`, or a table that cannot be turned into
    euros (no currency, or USD without its exchange rate).
    """
    used = {
        PriceComponent.INPUT: tokens.input,
        PriceComponent.OUTPUT: tokens.output,
        PriceComponent.CACHE_WRITE: tokens.cache_write,
        PriceComponent.CACHE_READ: tokens.cache_read,
    }
    if any(count < 0 for count in used.values()):
        raise ValueError(f"negative token count: {tokens}")
    # `price_at` goes first: it validates the instant and the history (naive datetime, duplicated dates).
    listed = price_at(tables, model_id, PriceComponent.INPUT, at)
    table = _in_force(tables, at)
    if table is None or listed is None:
        return None

    amount = Decimal(0)
    for component, count in used.items():
        if count == 0:
            continue
        price = price_at(tables, model_id, component, at)
        if price is None:
            raise ValueError(
                f"{model_id} has no {component.value} price in table {table.effective_from}: "
                "cache tokens are not free"
            )
        amount += price * count / _PER
    return CallCost(amount, table.currency or "", _to_eur(amount, table), table.effective_from.isoformat())


def total_eur(costs: Iterable[CallCost]) -> Decimal:
    """Exact sum in euros. Each cost keeps the exchange rate of its own table (contract §3.2)."""
    return sum((cost.eur for cost in costs), Decimal(0))


def presented(amount: Decimal, places: int = 2) -> Decimal:
    """Round ONCE, to show it: half up, to `places` decimals. The only rounding in the package (§3.5)."""
    return amount.quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP)


def period_total_eur(tables: Sequence[PriceTable], calls: Iterable[Call]) -> Decimal:
    """Exact cost in euros of every call of a period, each priced with the table in force at ITS instant.

    A monthly report that crosses a price change uses each stretch's table (contract §3.2), which falls out of
    pricing call by call. Raises `Unpriced` if any call has no price: a total that silently skips a call
    looks complete and is not.
    """
    costs = []
    for call in calls:
        cost = cost_of(tables, call.model_id, call.tokens, call.at)
        if cost is None:
            raise Unpriced(f"no table in force prices {call.model_id} at {call.at.isoformat()}")
        costs.append(cost)
    return total_eur(costs)
