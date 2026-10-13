"""R16: EVALGATE_SELF_GATE=off is valid while the active phase is < 9.

From F9 on, `off` is rejected: the repository may not opt out of its own gate. With `on` (the default
since F9) the repository goes behind its own gate: `evalgate eval self-gate` judges what today's code
gives from the recorded outputs against the published reports. Blocked is red.
"""

import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from gatelib import ROOT, active_phase

SELF_GATE_MANDATORY_FROM = 9  # RULES.md R16: retiring the escape hatch is an F9 deliverable

mode = os.environ.get("EVALGATE_SELF_GATE", "on")
phase = active_phase()
if mode not in {"on", "off"}:
    print(f"R16 FALLA · EVALGATE_SELF_GATE={mode!r}: solo 'on' u 'off'", file=sys.stderr)
    sys.exit(1)
if mode == "off" and phase >= SELF_GATE_MANDATORY_FROM:
    print(
        f"R16 FALLA · EVALGATE_SELF_GATE=off desde F{SELF_GATE_MANDATORY_FROM} no se admite", file=sys.stderr
    )
    sys.exit(1)
if mode == "on":
    done = subprocess.run(
        ["evalgate", "eval", "self-gate"], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if done.returncode != 0:
        why = "la puerta BLOQUEA este repositorio" if done.returncode == 1 else "no se pudo comparar"
        print(f"R16 FALLA · {why}\n{done.stdout}{done.stderr}", file=sys.stderr)
        sys.exit(1)
print(f"R16 ok · EVALGATE_SELF_GATE={mode}, fase {phase}")
