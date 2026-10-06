"""Price table data model. Mirrors docs/CONTRACTS/pricing-table.md §2."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum


class PriceComponent(StrEnum):
    """Billable token class. Cache write and cache read are priced separately (contract §3.3)."""

    INPUT = "input"
    OUTPUT = "output"
    CACHE_WRITE = "cache_write"
    CACHE_READ = "cache_read"


@dataclass(frozen=True, slots=True)
class ModelPrice:
    """Per-1k-token prices of one model, in the currency of its table."""

    input_per_1k: Decimal
    output_per_1k: Decimal
    cache_write_per_1k: Decimal | None = None
    cache_read_per_1k: Decimal | None = None


@dataclass(frozen=True, slots=True)
class Fx:
    """The exchange rate a table was priced with, and its date. Without both, euros are not reproducible."""

    usd_eur: Decimal
    fx_date: date


@dataclass(frozen=True, slots=True)
class PriceTable:
    """One pricing/<YYYY-MM-DD>.yaml file. Never edited once published (R4).

    `currency` and `fx` have no default VALUE on purpose: a table that does not say its currency cannot be
    turned into euros, and `cost_of` refuses it rather than assume one (R3: no price lives in the code, and an
    assumed exchange rate would be exactly that).
    """

    effective_from: date
    models: Mapping[str, ModelPrice]
    currency: str | None = None  # "USD" | "EUR"
    fx: Fx | None = None
