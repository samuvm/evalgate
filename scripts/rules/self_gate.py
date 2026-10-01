"""R16: EVALGATE_SELF_GATE=off is valid while the active phase is < 9.

From F9 on, `off` requires an approved proposal in docs/PARA-SAMUEL.md that mentions EVALGATE_SELF_GATE.
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gatelib import ROOT, active_phase

SELF_GATE_MANDATORY_FROM = 9  # RULES.md R16 and PLAN.md F9: retiring the escape hatch is an F9 deliverable

mode = os.environ.get("EVALGATE_SELF_GATE", "off")
phase = active_phase()
if mode not in {"on", "off"}:
    print(f"R16 FALLA · EVALGATE_SELF_GATE={mode!r}: solo 'on' u 'off'", file=sys.stderr)
    sys.exit(1)
if mode == "off" and phase >= SELF_GATE_MANDATORY_FROM:
    proposals = (ROOT / "docs/PARA-SAMUEL.md").read_text(encoding="utf-8").split("## PROPUESTA ")[1:]
    if not any("EVALGATE_SELF_GATE" in p and "Estado: APROBADA" in p for p in proposals):
        print(f"R16 FALLA · EVALGATE_SELF_GATE=off en fase {phase} sin propuesta aprobada", file=sys.stderr)
        sys.exit(1)
print(f"R16 ok · EVALGATE_SELF_GATE={mode}, fase {phase}")
