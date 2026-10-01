"""R19: [tool.gate] line coverage and mutation minimums equal G-LINE-COV and G-MUTATION, same unit.

pyproject.toml is not in `deny`, so an agent could lower these two numbers without touching GOALS.yaml.
GOALS.yaml wins: any difference, or a unit other than `porcentaje`, fails.
"""

import sys

from gatelib import goal, tool_gate

PAIRS = {"cobertura_linea_min": "G-LINE-COV", "mutantes_muertos_min": "G-MUTATION"}

errors: list[str] = []
gate = tool_gate()
for key, goal_id in PAIRS.items():
    umbral = goal(goal_id)["umbral"]
    if umbral.get("unidad") != "porcentaje":
        errors.append(f"{goal_id}: unidad {umbral.get('unidad')!r}, se esperaba 'porcentaje'")
    if gate.get(key) != umbral["valor"]:
        errors.append(
            f"[tool.gate].{key}={gate.get(key)!r} != {goal_id}={umbral['valor']!r} (manda GOALS.yaml)"
        )

for error in errors:
    print(f"R19 FALLA · {error}", file=sys.stderr)
if not errors:
    print("R19 ok · [tool.gate] coincide con G-LINE-COV y G-MUTATION")
sys.exit(1 if errors else 0)
