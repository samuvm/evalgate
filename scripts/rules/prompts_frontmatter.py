"""RULES §2: el gate rechaza un prompt sin frontmatter. Y un prompt escrito dentro del código.

1. Todo `prompts/*.md` carga con `evalgate.evals.prompts.load_prompt`: frontmatter completo (id, version,
   modelo_destino, temperatura, cambios), nombre de fichero igual al id y cuerpo no vacío.
2. Ningún módulo de `src/evalgate/` contiene un prompt en línea: un literal de texto largo que hable a un
   modelo en segunda persona ("Eres un…", "You are a…"). Es una heurística, y por eso es estrecha: lo que
   busca es el prompt pegado en el cliente del juez "solo para probar".
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from evalgate.evals.prompts import PromptError, load_prompt  # noqa: E402 - after the path line above

OPENERS = ("eres un", "eres una", "you are a", "you are an", "actúa como", "act as")
problems: list[str] = []
prompts = sorted((ROOT / "prompts").glob("*.md"))
for path in prompts:
    try:
        load_prompt(path)
    except PromptError as refused:
        problems.append(str(refused))

for path in sorted((ROOT / "src" / "evalgate").rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
    }
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Constant) and isinstance(node.value, str)) or id(node) in docstrings:
            continue
        if node.value.strip().lower().startswith(OPENERS):
            problems.append(f"{path.relative_to(ROOT)}:{node.lineno} prompt en línea: va en prompts/<id>.md")

for problem in problems:
    print(f"PROMPTS FALLA · {problem}", file=sys.stderr)
if not problems:
    print(f"prompts ok · {len(prompts)} prompt(s) con frontmatter completo y ninguno escrito en el código")
sys.exit(1 if problems else 0)
