"""Prepara una tanda de etiquetado humano para la kappa del juez.

Toma respuestas YA GRABADAS de varias variantes del sistema bajo prueba y escribe los 50 casos que se
etiquetan con `scripts/label_cases.py`. Cada caso es exactamente lo que vio el juez: las fichas (o el
contexto recortado), la pregunta y la respuesta.

Dos reglas de diseño, las dos para que la kappa signifique algo:

- **La mezcla es por variante, nunca por veredicto del juez.** Elegir los casos mirando qué dijo el juez
  sesgaría la concordancia que se quiere medir. Se usa el golden v2 (ADR-017): en el v1 el juez decía
  FIEL en casi todo y con una sola clase la kappa no está definida.
- **Lo que identifica el caso va aparte.** `tanda-N.items.jsonl` (lo que se enseña) no dice de qué variante
  ni de qué caso del golden sale cada respuesta; eso queda en `tanda-N.key.jsonl`, que el etiquetador no lee.

La tanda 2 excluye los casos de la tanda 1. Determinista (semilla fija). No llama a ningún modelo.

Uso: python scripts/prepare_labels.py --tanda 1
"""

import argparse
import hashlib
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GOLDEN = ROOT / "evals" / "golden" / "rag-app-v2"
SUT = ROOT / "evals" / "suites" / "rag-app-v2" / "sut"
LABELS = GOLDEN / "labels"
SEED = 20261007
# 50 casos por tanda. Fijada antes de mirar qué dice el juez de cada caso: la línea base y las cuatro
# degradaciones canónicas, con más peso para la base porque es lo que la puerta ve más a menudo.
MIX = {"base": 14, "contexto-50": 9, "modelo-pequeno": 9, "docs-aleatorios-20": 9, "temperatura-1.2": 9}


def jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tanda", type=int, required=True, choices=[1, 2])
    args = parser.parse_args()
    items_path = LABELS / f"tanda-{args.tanda}.items.jsonl"
    if items_path.exists():
        print(
            f"{items_path.relative_to(ROOT)} ya existe: una tanda preparada no se regenera.", file=sys.stderr
        )
        return 2
    missing = [name for name in MIX if not (SUT / f"{name}.jsonl").exists()]
    if missing:
        print(
            f"faltan salidas grabadas de: {', '.join(missing)} (make eval-refresh VARIANT=…)", file=sys.stderr
        )
        return 2

    questions = {str(row["id"]): row for row in jsonl(GOLDEN / "questions.jsonl")}
    fichas = {str(row["id"]): row for row in jsonl(GOLDEN / "corpus.jsonl")}
    taken = {
        (str(row["variant"]), str(row["case_id"]))
        for other in LABELS.glob("tanda-*.key.jsonl")
        for row in jsonl(other)
    }
    rng = random.Random(f"{SEED}:{args.tanda}")  # noqa: S311 - reproducible sample, not cryptography
    chosen: list[tuple[str, dict[str, object]]] = []
    for variant, count in MIX.items():
        free = [row for row in jsonl(SUT / f"{variant}.jsonl") if (variant, str(row["id"])) not in taken]
        chosen += [(variant, row) for row in rng.sample(free, count)]
    rng.shuffle(chosen)

    items, key = [], []
    for position, (variant, row) in enumerate(chosen):
        case_id = str(row["id"])
        context = row.get("context")
        if context is None:
            context = "\n".join(json.dumps(fichas[str(f)], ensure_ascii=False) for f in row["retrieved"])  # type: ignore[union-attr]
        shown = {"contexto": context, "pregunta": questions[case_id]["pregunta"], "respuesta": row["answer"]}
        digest = (
            "sha256:"
            + hashlib.sha256(json.dumps(shown, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
        )
        item_id = f"t{args.tanda}-{position:02d}"
        items.append({"item_id": item_id, **shown, "item_sha256": digest})
        key.append({"item_id": item_id, "variant": variant, "case_id": case_id, "item_sha256": digest})

    LABELS.mkdir(parents=True, exist_ok=True)
    items_path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in items), "utf-8")
    (LABELS / f"tanda-{args.tanda}.key.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in key), "utf-8"
    )
    print(f"tanda {args.tanda}: {len(items)} casos ({MIX}) -> {items_path.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
