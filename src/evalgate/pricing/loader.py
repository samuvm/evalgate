"""Loading of `pricing/<YYYY-MM-DD>.yaml` (docs/CONTRACTS/pricing-table.md §2, docs/spec/pricing-table.schema.json).

A file becomes a `PriceTable` only if it is exactly what the contract describes AND exactly what was
published. Two decisions carry that:

- **The price is the digits in the file.** The YAML is read with every scalar as text and prices go straight
  into `Decimal`: they never pass through a `float`, so `0.1` is 0.1 and what is priced is what was written.
- **Sealed or refused (R4).** `load_tables` checks every file against `pricing/TABLES.lock` BEFORE reading it.
  An edited table, a deleted one and one nobody sealed are all refused: each would change, silently, a
  report that was already priced.

The schema's three rules that JSON Schema cannot express are enforced here: file name = `effective_from`, no
duplicated model, digest in the lock. Validation is by hand because `jsonschema` is a dev dependency; the
contract test holds this loader and the schema to the same examples.
"""

import hashlib
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import yaml

from evalgate.pricing.model import Fx, ModelPrice, PriceTable

_TABLE_KEYS = {"effective_from", "source", "retrieved_at", "currency", "fx", "models"}
_FX_KEYS = {"USD_EUR", "fx_date"}
_MODEL_REQUIRED = {"id", "provider", "region", "input_per_1k", "output_per_1k"}
_MODEL_OPTIONAL = {"cache_write_per_1k", "cache_read_per_1k", "note"}
_CURRENCIES = {"USD", "EUR"}


class TableError(ValueError):
    """A price table that cannot be trusted: malformed, misnamed, duplicated or not the one that was published."""


def _fields(node: Any, required: set[str], optional: set[str], where: str) -> dict[str, Any]:
    if not isinstance(node, dict):
        raise TableError(f"{where}: se esperaba un mapping")
    if missing := sorted(required - node.keys()):
        raise TableError(f"{where}: falta {', '.join(missing)}")
    if extra := sorted(node.keys() - required - optional):
        raise TableError(f"{where}: campo no admitido {', '.join(extra)}")
    return node


def _day(value: Any, field: str, where: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError):
        raise TableError(f"{where}: {field} no es una fecha AAAA-MM-DD ({value!r})") from None


def _amount(value: Any, field: str, where: str, *, positive: bool = False) -> Decimal:
    try:
        number = Decimal(value)
    except (TypeError, ValueError, InvalidOperation):
        raise TableError(f"{where}: {field} no es un número ({value!r})") from None
    if not number.is_finite() or number < 0 or (positive and number == 0):
        raise TableError(f"{where}: {field} fuera de rango ({value!r})")
    return number


def _text(value: Any, field: str, where: str) -> str:
    if not isinstance(value, str) or not value:
        raise TableError(f"{where}: {field} vacío o no es texto")
    return value


def _model(node: Any, where: str) -> tuple[str, ModelPrice]:
    fields = _fields(node, _MODEL_REQUIRED, _MODEL_OPTIONAL, where)
    model_id = _text(fields["id"], "id", where)
    where = f"{where} ({model_id})"

    def optional(field: str) -> Decimal | None:
        return _amount(fields[field], field, where) if field in fields else None

    return model_id, ModelPrice(
        _amount(fields["input_per_1k"], "input_per_1k", where),
        _amount(fields["output_per_1k"], "output_per_1k", where),
        optional("cache_write_per_1k"),
        optional("cache_read_per_1k"),
        _text(fields["provider"], "provider", where),
        _text(fields["region"], "region", where),
    )


def parse_table(text: str, filename: str) -> PriceTable:
    """The table written in `text`, which must be the content of a file called `filename`. Raises TableError."""
    try:
        # BaseLoader: every scalar stays the text that was written. No float ever touches a price.
        # It builds only str, list and dict: stricter than `safe_load`, which would already turn 0.0008 into a float.
        loader = yaml.BaseLoader(text)
        try:
            document = loader.get_single_data()
        finally:
            loader.dispose()
    except yaml.YAMLError as exc:
        raise TableError(f"{filename}: YAML ilegible ({type(exc).__name__})") from None
    fields = _fields(document, _TABLE_KEYS, set(), filename)

    effective_from = _day(fields["effective_from"], "effective_from", filename)
    if filename != f"{effective_from.isoformat()}.yaml":
        raise TableError(f"{filename}: el nombre no coincide con effective_from ({effective_from.isoformat()})")
    _day(fields["retrieved_at"], "retrieved_at", filename)
    if not str(fields["source"]).startswith(("https://", "http://")):
        raise TableError(f"{filename}: source no es una URL pública ({fields['source']!r})")
    if fields["currency"] not in _CURRENCIES:
        raise TableError(f"{filename}: currency debe ser USD o EUR ({fields['currency']!r})")
    fx = _fields(fields["fx"], _FX_KEYS, set(), f"{filename} fx")
    rate = Fx(_amount(fx["USD_EUR"], "USD_EUR", filename, positive=True), _day(fx["fx_date"], "fx_date", filename))

    if not isinstance(fields["models"], list) or not fields["models"]:
        raise TableError(f"{filename}: models vacío: una tabla sin modelos no pone precio a nada")
    models: dict[str, ModelPrice] = {}
    for position, node in enumerate(fields["models"]):
        model_id, price = _model(node, f"{filename} models[{position}]")
        if model_id in models:
            # Also refuses the same id under another provider or region, which the schema allows: `price_at`
            # resolves by id alone and would silently pick one of the two (ADR-013).
            raise TableError(f"{filename}: el modelo {model_id} aparece dos veces")
        models[model_id] = price
    return PriceTable(effective_from, models, fields["currency"], rate)


def _sealed(lock: Path) -> dict[str, str]:
    """`<sha256>  pricing/<name>` per line, the format of `shasum -a 256`. Keyed by bare file name."""
    entries: dict[str, str] = {}
    for line in lock.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, name = line.split(maxsplit=1)
            entries[Path(name.strip()).name] = digest
    return entries


def load_tables(directory: Path, lock: Path) -> list[PriceTable]:
    """Every published table of `directory`, oldest first. Raises TableError unless the directory is exactly
    what `lock` sealed: nothing edited, nothing missing, nothing extra."""
    files = {path.name: path.read_bytes() for path in sorted(directory.glob("*.yaml"))}
    if not lock.exists():
        if files:
            raise TableError(f"hay tablas en {directory.name}/ y no existe {lock.name}: ninguna está publicada")
        return []
    sealed = _sealed(lock)
    for name in sorted(sealed.keys() - files.keys()):
        raise TableError(f"{name} está sellada en {lock.name} y ya no existe")
    tables = []
    for name, content in files.items():
        if name not in sealed:
            raise TableError(f"{name} no está sellada en {lock.name}: no está publicada")
        if hashlib.sha256(content).hexdigest() != sealed[name]:
            raise TableError(f"{name} cambió tras publicarse: una tabla publicada no se edita (R4)")
        tables.append(parse_table(content.decode("utf-8"), name))
    return sorted(tables, key=lambda table: table.effective_from)
