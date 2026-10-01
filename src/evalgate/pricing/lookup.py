"""Resolution of the price in force at a given instant (docs/CONTRACTS/pricing-table.md §2)."""

from collections.abc import Sequence
from datetime import UTC, datetime, time
from decimal import Decimal

from evalgate.pricing.model import PriceComponent, PriceTable


def price_at(
    tables: Sequence[PriceTable], model_id: str, component: PriceComponent, at: datetime
) -> Decimal | None:
    """Per-1k price of `component` for `model_id` in the table in force at `at`.

    The table in force is the one with the most recent `effective_from` <= `at`, where
    `effective_from` starts at 00:00:00 UTC of that day. Never the current table.

    Raises ValueError if `at` has no timezone (the instant would be ambiguous) or if two tables share an
    `effective_from` (one file per date: the contract makes it impossible, so it is corrupt input).
    """
    if at.tzinfo is None or at.utcoffset() is None:
        raise ValueError("price_at needs a timezone-aware instant")
    starts = [t.effective_from for t in tables]
    if len(starts) != len(set(starts)):
        raise ValueError("two price tables share the same effective_from")
    in_force = [t for t in tables if datetime.combine(t.effective_from, time.min, UTC) <= at]
    if not in_force:
        return None
    price = max(in_force, key=lambda t: t.effective_from).models.get(model_id)
    if price is None:
        return None
    by_component: dict[PriceComponent, Decimal | None] = {
        PriceComponent.INPUT: price.input_per_1k,
        PriceComponent.OUTPUT: price.output_per_1k,
        PriceComponent.CACHE_WRITE: price.cache_write_per_1k,
        PriceComponent.CACHE_READ: price.cache_read_per_1k,
    }
    return by_component[component]
