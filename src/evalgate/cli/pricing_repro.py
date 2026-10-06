"""`evalgate eval pricing-repro`: G-PRICE-REPRO. I/O and wiring only (RULES §2: excluded from unit tests, held
by tests/contract/test_pricing_repro.py).

Recomputes every report of the fixed corpus with the price table in force AT THE DATE of each call
(`pricing.cost.period_total_eur`) and compares it, exactly, with the total the report recorded. The number
published is the largest difference in euros, and the only passing value is 0: with `Decimal` end to end
there is no tolerance to hide behind.
"""

import hashlib
import json
import platform
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import yaml

from evalgate.pricing.cost import Call, Tokens, period_total_eur
from evalgate.pricing.loader import load_tables

GOAL = "G-PRICE-REPRO"
SUITE = "pricing-repro"


def _digest(path: Path) -> str:
    # `sha256:<hex>`, the digest notation: a bare hex string is what detect-secrets takes for a key.
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _exact(amount: Decimal) -> str:
    """Every digit and no trailing zeros, never scientific notation: `0.0135`, `0`."""
    return format(amount.normalize(), "f")


def _calls(report: dict[str, Any]) -> list[Call]:
    return [
        Call(
            datetime.fromisoformat(call["at"]),
            call["model"],
            Tokens(
                int(call["input"]),
                int(call["output"]),
                int(call.get("cache_write", 0)),
                int(call.get("cache_read", 0)),
            ),
        )
        for call in report["calls"]
    ]


def run(suite_dir: Path, out: Path) -> Decimal:
    """Write the eval report (docs/CONTRACTS/eval-report.schema.json) and its per-case detail next to it.
    Returns the largest |recomputed - recorded| in euros."""
    corpus = suite_dir / "reports.yaml"
    tables = load_tables(suite_dir / "tables", suite_dir / "TABLES.lock")
    # BaseLoader: totals and counts stay the text that was written; nothing passes through a float.
    loader = yaml.BaseLoader(corpus.read_text(encoding="utf-8"))
    try:
        reports = loader.get_single_data()["reports"]
    finally:
        loader.dispose()

    cases = []
    for report in reports:
        recorded = Decimal(report["recorded_total_eur"])
        recomputed = period_total_eur(tables, _calls(report))
        cases.append(
            {
                "id": report["id"],
                "regla": report["regla"],
                "recorded_total_eur": _exact(recorded),
                "recomputed_total_eur": _exact(recomputed),
                "diff_eur": _exact(abs(recomputed - recorded)),
                "match": recomputed == recorded,
            }
        )
    worst = max((Decimal(case["diff_eur"]) for case in cases), default=Decimal(0))

    raw = out.with_name(f"{out.stem}-cases.json")
    raw.write_text(json.dumps(cases, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    dataset, lock = _digest(corpus), _digest(suite_dir / "TABLES.lock")
    document = {
        "contract_version": 1,
        # Deterministic: the same corpus and the same sealed tables are the same run.
        "run_id": f"{SUITE}-{hashlib.sha256((dataset + lock).encode()).hexdigest()[:16]}",
        "project": "evalgate",
        "suite": SUITE,
        "created_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "environment": {
            "hardware": f"{platform.machine()} · {platform.platform()}",
            "python": platform.python_version(),
            "deterministic": True,
            "tables_lock": lock,
        },
        "dataset": {"name": SUITE, "version": 1, "n_cases": len(cases), "sha256": dataset},
        "metrics": [
            {"id": GOAL, "value": float(worst), "n": len(cases), "unit": "eur", "raw_path": str(raw.name)}
        ],
        "notes": (
            f"Diferencia máxima al recalcular: {_exact(worst * 100)} céntimos. "
            f"{sum(case['match'] for case in cases)} de {len(cases)} informes coinciden exactamente. "
            "Corpus y tablas sintéticos y declarados (evals/suites/pricing-repro/). "
            "Los totales registrados se calcularon a mano."
        ),
    }
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return worst
