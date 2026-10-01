"""DoD #10 and anti-gaming #3: debt markers in src/ <= 10, and zero skip/xfail anywhere in tests/.

The constitution allows a skip with a ticket in STATE.md; this project is stricter and allows none.
tests/holdout/ is excluded: the builder never reads it.
"""

import ast
import re
import sys

from gatelib import ROOT

MAX_DEBT = 10  # CONSTITUCION §5 #10
DEBT = re.compile(r"\b(TODO|FIXME|XXX|NotImplementedError)\b")
ESCAPES = {"skip", "skipif", "xfail", "importorskip"}

debt = [
    f"{path.relative_to(ROOT)}:{n}"
    for path in sorted((ROOT / "src").rglob("*.py"))
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
    if DEBT.search(line)
]

escapes: list[str] = []
holdout = ROOT / "tests" / "holdout"
for path in sorted((ROOT / "tests").rglob("*.py")):
    if holdout in path.parents:
        continue
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Attribute) and node.attr in ESCAPES:
            escapes.append(f"{path.relative_to(ROOT)}:{node.lineno} · {node.attr}")

for item in escapes:
    print(f"ANTI-GAMING · escape de la suite prohibido · {item}", file=sys.stderr)
if len(debt) > MAX_DEBT:
    print(f"DEUDA · {len(debt)} marcas en src/ > {MAX_DEBT}: {', '.join(debt)}", file=sys.stderr)
print(f"deuda_src={len(debt)} escapes_tests={len(escapes)}")
sys.exit(1 if escapes or len(debt) > MAX_DEBT else 0)
