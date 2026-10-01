"""Our own ClickHouse migrations (`create_schema: false`, RULES §3.13): the schema is versioned here, never
created on the fly by an exporter.

A migration is history once applied, with the same rule as a published price table (R4): editing it is
refused, and a fix is a NEW numbered file. `schema_migrations` keeps the sha256 of what was run.
"""

import hashlib
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from evalgate.telemetry.exporters import StoreClient

MIGRATIONS = Path(__file__).parent / "sql"
LEDGER = "schema_migrations"
_LEDGER_DDL = (
    f"CREATE TABLE IF NOT EXISTS {LEDGER} "
    "(version String, name String, sha256 String, applied_at DateTime64(3) DEFAULT now64(3)) "
    "ENGINE = MergeTree ORDER BY version"
)
_FILE = re.compile(r"^(\d{4})_([a-z0-9_]+)\.sql$")


class MigrationTampered(RuntimeError):
    """An applied migration no longer matches what was applied. Never "fixed" automatically."""


@dataclass(frozen=True, slots=True)
class Migration:
    version: str
    name: str
    sql: str

    @property
    def sha256(self) -> str:
        return hashlib.sha256(self.sql.encode("utf-8")).hexdigest()


def available(directory: Path) -> list[Migration]:
    """The `NNNN_name.sql` files of `directory`, in version order."""
    found = []
    for path in sorted(directory.glob("*.sql")):
        if match := _FILE.match(path.name):
            found.append(Migration(match[1], match[2], path.read_text(encoding="utf-8")))
    return found


def pending(applied: Mapping[str, str], migrations: Sequence[Migration]) -> list[Migration]:
    """What is left to run. Raises if something already run has changed since."""
    for migration in migrations:
        digest = applied.get(migration.version)
        if digest is not None and digest != migration.sha256:
            raise MigrationTampered(
                f"migración {migration.version} ({migration.name}) editada tras aplicarse: "
                f"sha256 aplicado {digest[:12]}…, en disco {migration.sha256[:12]}…. "
                "Se corrige con una nueva."
            )
    return [m for m in migrations if m.version not in applied]


def statements(sql: str) -> list[str]:
    """Split a file into statements on the `;` that ends a line. Our files keep `;` out of literals."""
    return [part.strip() for part in re.split(r";\s*$", sql, flags=re.MULTILINE) if part.strip()]


def apply(client: StoreClient, directory: Path = MIGRATIONS) -> list[Migration]:
    """Run the pending migrations in order and record each one. Idempotent: a second run does nothing."""
    client.command(_LEDGER_DDL)
    applied = {
        str(version): str(digest)
        for version, digest in client.query(
            f"SELECT version, sha256 FROM {LEDGER}"  # noqa: S608 - constant table name, no input
        ).result_rows
    }
    todo = pending(applied, available(directory))
    for migration in todo:
        for statement in statements(migration.sql):
            client.command(statement)
        client.insert(
            LEDGER,
            [[migration.version, migration.name, migration.sha256]],
            column_names=("version", "name", "sha256"),
        )
    return todo
