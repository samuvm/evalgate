"""R7: la puerta no contiene un solo umbral literal. Todo parámetro de decisión llega de configuración.

Por AST sobre `src/evalgate/gate/decision.py`: falla ante CUALQUIER literal numérico (entero, flotante o
complejo), sin lista de excepciones. Ni el 0,95 del intervalo, ni el 3 de "más de tres métricas", ni un
inocente 0 o 1: el día que un número aparece en la decisión, alguien ha decidido algo sin pasar por
`GOALS.yaml`. Lo que la decisión necesita y parece un número (la cola del intervalo, "empeoró") tiene nombre
y vive en `stats/`, con sus tests.

Regla hermana, escrita a propósito: tampoco se admite fabricar un número sin escribirlo —`float()`, `int()`,
`Fraction(True)`, `len("ab")`—. Es la misma decisión con disfraz, y ya pasó una vez (2026-10-06).
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DECISION = ROOT / "src" / "evalgate" / "gate" / "decision.py"
NUMBER_MAKERS = {"int", "float", "complex", "Fraction", "Decimal", "len", "bool"}

problems: list[str] = []
for node in ast.walk(ast.parse(DECISION.read_text(encoding="utf-8"))):
    line = getattr(node, "lineno", "?")
    if isinstance(node, ast.Constant) and isinstance(node.value, int | float | complex):
        if isinstance(node.value, bool):
            continue  # True/False como valores lógicos; como argumento de un constructor numérico, abajo
        problems.append(f"{line} literal numérico {node.value!r}")
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in NUMBER_MAKERS:
        constant_args = all(isinstance(arg, ast.Constant) for arg in node.args)
        if constant_args and not node.keywords:
            problems.append(f"{line} número fabricado con {node.func.id}(...) sobre constantes")

where = DECISION.relative_to(ROOT)
for problem in problems:
    print(f"R7 FALLA · {where}:{problem}. Los parámetros de la decisión llegan en Policy", file=sys.stderr)
if not problems:
    print(f"R7 ok · {where} sin un solo umbral literal ni número fabricado")
sys.exit(1 if problems else 0)
