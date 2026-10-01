"""Synthetic, self-verifying corpus for examples/rag-app (PARA-SAMUEL Q-002 (a)).

Each record ("ficha") describes a fictional product. Questions are generated from the same fields, so the
correct answer is known by construction: no human labelling, fully reproducible from the seed.
provenance = "sintetico_por_construccion". It measures whether the gate detects degradations, not domain
quality.

Usage: python generate_corpus.py [--fichas 40] [--questions 20] [--seed 20260910] [--out DIR]
Standard library only: this app is a client and must not depend on evalgate (RULES R13).
"""

import argparse
import json
import random
from pathlib import Path

SYLLABLES = ["ka", "lo", "mi", "zu", "te", "ra", "no", "vi", "sa", "qu", "de", "fo", "ri", "ba", "xe"]
CATEGORIES = [
    "sensor de humedad",
    "bomba de riego",
    "lámpara de cultivo",
    "estación meteorológica",
    "válvula",
]
COUNTRIES = ["Portugal", "Chile", "Noruega", "Kenia", "Vietnam", "Uruguay", "Estonia", "Marruecos"]
FIELDS = {
    "precio_eur": ("¿Cuál es el precio en euros del {name}?", "{v} €"),
    "peso_g": ("¿Cuánto pesa, en gramos, el {name}?", "{v} g"),
    "autonomia_h": ("¿Cuántas horas de autonomía tiene el {name}?", "{v} h"),
    "anio": ("¿En qué año se fabricó el {name}?", "{v}"),
    "pais": ("¿En qué país se fabrica el {name}?", "{v}"),
    "garantia_meses": ("¿Cuántos meses de garantía tiene el {name}?", "{v} meses"),
}
NOT_IN_CORPUS = "NO_CONSTA"


def model_name(rng: random.Random, used: set[str]) -> str:
    while True:
        name = "".join(rng.choice(SYLLABLES) for _ in range(3)).capitalize() + f"-{rng.randint(100, 999)}"
        if name not in used:
            used.add(name)
            return name


def generate(
    n_fichas: int, n_questions: int, seed: int
) -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    rng = random.Random(seed)
    used: set[str] = set()
    fichas: list[dict[str, object]] = []
    for i in range(n_fichas):
        fichas.append(
            {
                "id": f"ficha-{i:04d}",
                "nombre": model_name(rng, used),
                "categoria": rng.choice(CATEGORIES),
                "precio_eur": rng.randint(12, 950),
                "peso_g": rng.randint(80, 9000),
                "autonomia_h": rng.randint(2, 400),
                "anio": rng.randint(2015, 2026),
                "pais": rng.choice(COUNTRIES),
                "garantia_meses": rng.choice([6, 12, 18, 24, 36]),
            }
        )

    questions: list[dict[str, object]] = []
    n_negative = max(1, round(n_questions * 0.2))  # contract retrieval-metrics §3: >= 15 % negatives
    for q in range(n_questions - n_negative):
        ficha = rng.choice(fichas)
        field = rng.choice(sorted(FIELDS))
        template, answer = FIELDS[field]
        questions.append(
            {
                "id": f"q-{q:04d}",
                "pregunta": template.format(name=ficha["nombre"]),
                "respuesta_referencia": answer.format(v=ficha[field]),
                "refs": [ficha["id"]],
                "tipo": "positivo",
                "provenance": "sintetico_por_construccion",
            }
        )
    for q in range(n_questions - n_negative, n_questions):
        field = rng.choice(sorted(FIELDS))
        questions.append(
            {
                "id": f"q-{q:04d}",
                "pregunta": FIELDS[field][0].format(name=model_name(rng, used)),
                "respuesta_referencia": NOT_IN_CORPUS,
                "refs": [],
                "tipo": "negativo",
                "provenance": "sintetico_por_construccion",
            }
        )
    return fichas, questions


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fichas", type=int, default=40)
    parser.add_argument("--questions", type=int, default=20)
    parser.add_argument("--seed", type=int, default=20260910)
    parser.add_argument("--out", type=Path, default=Path(__file__).parent / "data")
    args = parser.parse_args()
    fichas, questions = generate(args.fichas, args.questions, args.seed)
    args.out.mkdir(parents=True, exist_ok=True)
    for name, rows in (("corpus.jsonl", fichas), ("questions.jsonl", questions)):
        with (args.out / name).open("w", encoding="utf-8") as fh:
            fh.writelines(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    print(f"{len(fichas)} fichas, {len(questions)} preguntas -> {args.out}")


if __name__ == "__main__":
    main()
