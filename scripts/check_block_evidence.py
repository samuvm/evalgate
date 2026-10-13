"""G-GATE-BLOCK-EVIDENCE: the gate blocked a real regression, and docs/evidence/gate-blocks.md shows it.

Until a public pull request can be pointed at, the evidence is an entry with the before/after table of
an injected regression, the decision of the gate and the snapshot to return to. An entry counts if its
title says `BLOQUEO DE LA PUERTA` and it has all of:

  - a table with a column "Antes" and a column "Después";
  - a line "Decisión de la puerta: BLOCK";
  - a line "Snapshot: `.snapshots/<...>`" naming a directory that exists.

Prints `G-GATE-BLOCK-EVIDENCE n_bloqueos_documentados=<n>`; exit 1 unless n holds the threshold of GOALS.yaml.
"""

import re
import sys
from pathlib import Path

from gatelib import ROOT, goal

TITLE = "BLOQUEO DE LA PUERTA"


def _is_evidence(entry: str, root: Path) -> bool:
    headers = [line.lower() for line in entry.splitlines() if line.startswith("|")]
    has_table = any("antes" in line and "después" in line for line in headers)
    blocked = re.search(r"^Decisión de la puerta:\W*BLOCK\b", entry, re.M) is not None
    snapshot = re.search(r"^Snapshot:\s*`(\.snapshots/[^`]+)`", entry, re.M)
    return has_table and blocked and snapshot is not None and (root / snapshot[1]).is_dir()


def documented_blocks(evidence: str, root: Path) -> int:
    entries = re.split(r"^## ", evidence, flags=re.M)[1:]
    return sum(TITLE in entry.splitlines()[0] and _is_evidence(entry, root) for entry in entries)


if __name__ == "__main__":
    found = documented_blocks(
        (ROOT / "docs" / "evidence" / "gate-blocks.md").read_text(encoding="utf-8"), ROOT
    )
    threshold = goal("G-GATE-BLOCK-EVIDENCE")["umbral"]
    print(f"G-GATE-BLOCK-EVIDENCE n_bloqueos_documentados={found}")
    if threshold["operador"] != ">=":
        sys.exit(f"G-GATE-BLOCK-EVIDENCE: operador {threshold['operador']!r} no previsto")
    sys.exit(0 if found >= threshold["valor"] else 1)
