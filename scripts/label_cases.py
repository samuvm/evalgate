"""Herramienta de etiquetado humano para la kappa del juez, en tandas de 50.

Qué hace: te enseña, uno a uno, lo mismo que ve el juez —las fichas que recuperó el sistema, la pregunta y
la respuesta— y te pide un veredicto con una tecla. Nada más. No enseña el veredicto del juez (sería
copiarle), ni la respuesta de referencia (el juez tampoco la ve: se juzga FIDELIDAD a las fichas, no si la
respuesta es correcta), ni de qué variante del sistema sale cada respuesta.

    uv run python scripts/label_cases.py --tanda 1        # empieza o retoma la tanda 1
    uv run python scripts/label_cases.py --tanda 1 --estado

Teclas:  f = FIEL    n = NO_FIEL    s = saltar por ahora    d = deshacer la última    q = guardar y salir

Criterio, que es literalmente el del prompt del juez (prompts/judge_faithfulness.md):
- FIEL si todo dato que afirma la respuesta está en las fichas, tal cual.
- NO_FIEL si afirma algún dato que no está en las fichas, o que las contradice.
- Si la respuesta dice NO_CONSTA: FIEL si las fichas no tienen el dato pedido, NO_FIEL si sí lo tienen.

Se puede dejar a medias: cada etiqueta se guarda al momento en `evals/golden/rag-app-v2/labels/`. El orden
es aleatorio con semilla fija, así que retomar sigue donde lo dejaste. Las etiquetas son tuyas: ningún script
escribe en esos ficheros y la kappa (F7) se calcula solo con lo que haya ahí.
"""

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "golden" / "rag-app-v2"
LABELS = GOLDEN / "labels"
KEYS = {"f": "FIEL", "n": "NO_FIEL"}


def jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


COLOR = sys.stdout.isatty() and "NO_COLOR" not in os.environ
FIELD = re.compile(r'"(\w+)":\s*(?:"([^"]*)"|(-?\d+(?:\.\d+)?))(?=\s*[,}])')
NAMES = {
    "nombre": "nombre",
    "categoria": "categoría",
    "precio_eur": "precio (€)",
    "peso_g": "peso (g)",
    "autonomia_h": "autonomía (h)",
    "anio": "año",
    "pais": "país",
    "garantia_meses": "garantía (meses)",
}
CUT = "✂ cortado"
LEGEND = "f = FIEL    n = NO_FIEL    s = saltar    d = deshacer    q = guardar y salir"


def paint(text: str, code: str) -> str:
    return f"\033[{code}m{text}\033[0m" if COLOR else text


def ficha(line: str) -> tuple[dict[str, str], bool]:
    """Los campos que se leen enteros de una ficha y si llegó cortada. No añade ni quita nada a lo que
    recibió el modelo: un campo a medias se enseña como cortado, que es como lo vio."""
    fields = {key: text or number for key, text, number in FIELD.findall(line)}
    return fields, not line.rstrip().endswith("}")


def show(item: dict[str, object], position: int, total: int) -> None:
    if COLOR:
        print("\033[2J\033[H", end="")  # pantalla limpia: un caso, una pantalla
    print(paint(f"\n  CASO {position} DE {total}", "1"))
    print(paint("  " + "─" * 96, "2"))

    fichas = [ficha(line) for line in str(item["contexto"]).splitlines() if line.strip()]
    keys = [key for key in dict.fromkeys(key for fields, _ in fichas for key in fields) if key != "id"]
    rows = [["", *(fields.get("id", "ficha") + (" ✂" if cut else "") for fields, cut in fichas)]]
    rows += [[NAMES.get(key, key), *(fields.get(key, CUT) for fields, _ in fichas)] for key in keys]
    widths = [max(len(row[column]) for row in rows) for column in range(len(rows[0]))]
    print(
        paint("\n  FICHAS que vio el sistema", "1")
        + paint("  (✂ = le llegó cortada; lo cortado no cuenta)", "2")
    )
    for number, row in enumerate(rows):
        cells = [cell.ljust(width) for cell, width in zip(row, widths, strict=True)]
        cells = [paint(cell, "33") if cell.strip() == CUT else cell for cell in cells]
        label, values = paint(cells[0], "2"), "   ".join(cells[1:])
        emphasis = "1;36" if number == 0 else "1" if row[0] == "nombre" else ""
        print(f"    {label}   {paint(values, emphasis) if emphasis else values}")
        if number == 0:
            print(paint("    " + "─" * (sum(widths) + 3 * len(widths)), "2"))

    print(paint("\n  PREGUNTA   ", "1") + str(item["pregunta"]))
    print(paint("  RESPUESTA  ", "1") + paint(str(item["respuesta"]), "1;32"))
    print(paint("\n  " + "─" * 96, "2"))
    print(paint("  " + LEGEND, "2"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Etiquetado humano para la kappa del juez.")
    parser.add_argument("--tanda", type=int, required=True, choices=[1, 2])
    parser.add_argument("--estado", action="store_true", help="Solo dice cuántas llevas.")
    args = parser.parse_args()

    items_path = LABELS / f"tanda-{args.tanda}.items.jsonl"
    labels_path = LABELS / f"tanda-{args.tanda}.labels.jsonl"
    items = jsonl(items_path)
    if not items:
        print(
            f"No existe {items_path.relative_to(ROOT)}: la tanda todavía no está preparada.", file=sys.stderr
        )
        return 2
    done = {str(row["item_id"]): row for row in jsonl(labels_path)}
    pending = [item for item in items if str(item["item_id"]) not in done]
    print(f"Tanda {args.tanda}: {len(done)} etiquetadas de {len(items)}. Quedan {len(pending)}.")
    if args.estado or not pending:
        if not pending:
            print("Tanda completa. Gracias: ya no hay que hacer nada más con este script.")
        return 0

    by_id = {str(item["item_id"]): item for item in items}
    history: list[str] = []
    queue = list(pending)
    while queue:
        item = queue[0]
        show(item, len(items) - len(queue) + 1, len(items))
        try:
            key = input("  Tu veredicto [f/n/s/d/q] y Enter: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            key = "q"
        if key == "q":
            break
        if key == "d":
            if not history:
                print("   No hay nada que deshacer en esta sesión.")
                continue
            undone = history.pop()
            kept = [row for row in jsonl(labels_path) if str(row["item_id"]) != undone]
            labels_path.write_text(
                "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in kept), "utf-8"
            )
            queue.insert(0, by_id[undone])
            print("   Deshecha la última etiqueta: te la vuelvo a enseñar.")
            continue
        if key == "s":
            queue.append(queue.pop(0))  # al final de la cola: volverá a salir
            continue
        if key not in KEYS:
            print("   Tecla no reconocida: f, n, s, d o q.")
            continue
        row = {
            "item_id": item["item_id"],
            "label": KEYS[key],
            "item_sha256": item["item_sha256"],
            "labelled_at": datetime.now(UTC).isoformat(timespec="seconds"),
            "labelled_by": "samuel",
        }
        LABELS.mkdir(parents=True, exist_ok=True)
        with labels_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
        history.append(str(item["item_id"]))
        queue.pop(0)

    total_done = len(jsonl(labels_path))
    print(f"\nGuardado. Llevas {total_done} de {len(items)} en la tanda {args.tanda}.")
    if total_done < len(items):
        print(f"Para seguir: uv run python scripts/label_cases.py --tanda {args.tanda}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
