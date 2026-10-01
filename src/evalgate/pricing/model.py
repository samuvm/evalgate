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
class PriceTable:
    """One pricing/<YYYY-MM-DD>.yaml file. Never edited once published (R4)."""

    effective_from: date
    models: Mapping[str, ModelPrice]
