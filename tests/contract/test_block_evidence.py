"""`scripts/check_block_evidence.py` (G-GATE-BLOCK-EVIDENCE): what counts as evidence of a block."""

import sys
from pathlib import Path

import pytest

from ._paths import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
from check_block_evidence import documented_blocks

ENTRY = """\
## 2026-10-13 · BLOQUEO DE LA PUERTA · una regresión inyectada

| Métrica | Antes | Después |
|---|---|---|
| answer_correct | 0,900 | 0,635 |

Decisión de la puerta: **BLOCK**
Snapshot: `.snapshots/verde`
"""


@pytest.fixture
def root(tmp_path: Path) -> Path:
    (tmp_path / ".snapshots" / "verde").mkdir(parents=True)
    return tmp_path


def test_an_entry_with_table_decision_and_snapshot_counts(root: Path) -> None:
    assert documented_blocks("# Bloqueos\n\n" + ENTRY + "\n## otra entrada\n\ntexto\n", root) == 1
    assert documented_blocks(ENTRY + "\n" + ENTRY, root) == 2


@pytest.mark.parametrize(
    "broken",
    [
        ENTRY.replace("BLOQUEO DE LA PUERTA", "una prueba"),
        ENTRY.replace("| Después |", "|"),
        ENTRY.replace("**BLOCK**", "**PASS**"),
        ENTRY.replace(".snapshots/verde", ".snapshots/no-existe"),
        ENTRY.replace("Snapshot: `.snapshots/verde`\n", ""),
    ],
)
def test_an_entry_missing_any_of_them_does_not(root: Path, broken: str) -> None:
    assert documented_blocks(broken, root) == 0
