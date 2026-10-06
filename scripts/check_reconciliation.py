"""G-COST-RECONCILE: days since the last reconciliation against a REAL provider invoice.

Not blocking: with local models only there is no paid key, no spend and so no
invoice. This script does not pretend otherwise: without a `docs/reconciliation-<AAAA-MM-DD>.md` it says that
no reconciliation exists and exits 1. The day there is a key, the artefact is written by hand from a real
invoice (contract pricing-table §5.2) and this prints its age, which is what the goal measures.

Reconciling against Ollama's own token counts would not be a reconciliation: there is no bill on the other
side. The automatable half of the old "1 %" lives in G-PRICE-REPRO.
"""

import re
import sys
from datetime import UTC, date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
found = sorted(
    date.fromisoformat(m[1])
    for p in (ROOT / "docs").glob("reconciliation-*.md")
    if (m := re.fullmatch(r"reconciliation-(\d{4}-\d{2}-\d{2})\.md", p.name))
)
if not found:
    print(
        "G-COST-RECONCILE sin_conciliacion=1 · no existe docs/reconciliation-<fecha>.md: coste real "
        "incurrido 0 EUR, solo modelos locales. No bloquea.",
        file=sys.stderr,
    )
    sys.exit(1)
days = (datetime.now(UTC).date() - found[-1]).days
print(f"G-COST-RECONCILE dias_desde_conciliacion={days} ultima={found[-1].isoformat()}")
