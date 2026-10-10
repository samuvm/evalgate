"""Regenerate `evals/golden/rag-app-v2/`: the HARDER golden set (ADR-017). Deterministic.

Why it exists: on v1 the base system scores 1.000 on everything, the judge said NO_FIEL in 6 of 497 verdicts
and two of the four canonical degradations change nothing. A corpus that easy leaves no room to measure a
judge's kappa, the gate's power or its false positives. v1 stays as it is: it backs the numbers of F5.

Same method (ADR-016): synthetic by construction, the right answer known because it is generated with the
ficha, `provenance: sintetico_por_construccion`. What changes is that the questions can be got wrong:

- **Siblings.** Products come in families of four with the same name and another number ("Xelote 179",
  "Xelote 197"…). The right ficha reaches the model next to its siblings, and it has to pick.
- `lookup`           one field of one product (as in v1, now among siblings).
- `comparacion`      "which is heavier, A or B?": two fichas, the answer is ONE name. `excluye` carries the
                     other, so an answer that names both is not correct.
- `filtro`           "of the products of category C made in country P in year Y, which is the most
                     expensive?": the system has to find them all first.
- `negativo-hermano` a product that does NOT exist whose siblings do. The honest answer is NO_CONSTA; the
                     tempting one is a sibling's datum.
- `negativo`         a product nobody resembles.

20 % of the cases are negative (contract retrieval-metrics §3 asks for at least 15 %). The kind of question
goes in `notas`, so results can be broken down by it.

The mix below was chosen BEFORE measuring anything on v2. If it is ever changed after seeing results, the
change and its reason go in the CHANGELOG: tuning a benchmark until it says what one wants is the thing
this repository exists to call out.

One change WAS made after the first measurement, and only to wording (2026-10-10): the `filtro`
questions asked "¿cuál es el más caro?" and the system, told to answer "only the datum asked for", gave the
PRICE of the right product in 32 of 50 cases. The question was ambiguous; scoring that as wrong measured the
wording, not the system. They now ask "¿cómo se llama el más caro?". The mix, the comparisons (whose errors
are real) and every other question are as first generated.

Usage: python scripts/gen_golden_v2.py
"""

import hashlib
import importlib.util
import json
import random
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "golden" / "rag-app-v2"
SEED, FAMILIES, SIBLINGS, N_CALIBRATION = 20261010, 40, 4, 60
MIX = {"lookup": 60, "comparacion": 50, "filtro": 50, "negativo-hermano": 25, "negativo": 15}  # 200 cases
DIFFICULTY = {
    "lookup": "facil",
    "comparacion": "media",
    "filtro": "dificil",
    "negativo-hermano": "media",
    "negativo": "facil",
}
COMPARE = {
    "precio_eur": "¿Cuál es más caro, el {a} o el {b}?",
    "peso_g": "¿Cuál pesa más, el {a} o el {b}?",
    "autonomia_h": "¿Cuál tiene más horas de autonomía, el {a} o el {b}?",
}
_AMONG = "De los productos de categoría «{cat}» fabricados en {pais} en {anio}, "
FILTER = {
    "precio_eur": _AMONG + "¿cómo se llama el más caro?",
    "peso_g": _AMONG + "¿cómo se llama el que pesa más?",
}

spec = importlib.util.spec_from_file_location(
    "generate_corpus", ROOT / "examples" / "rag-app" / "generate_corpus.py"
)
if spec is None or spec.loader is None:
    raise SystemExit("no se puede cargar examples/rag-app/generate_corpus.py")
vocabulary = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vocabulary)


def fichas_in_families(rng: random.Random) -> tuple[list[dict[str, object]], dict[str, list[int]]]:
    fichas: list[dict[str, object]] = []
    numbers: dict[str, list[int]] = {}
    while len(numbers) < FAMILIES:
        base = "".join(rng.choice(vocabulary.SYLLABLES) for _ in range(3)).capitalize()
        if base in numbers:
            continue
        numbers[base] = rng.sample(range(100, 1000), SIBLINGS + 1)  # the last one is never built: a near miss
        for number in numbers[base][:SIBLINGS]:
            fichas.append(
                {
                    "id": f"ficha-{len(fichas):04d}",
                    "nombre": f"{base} {number}",
                    "categoria": rng.choice(vocabulary.CATEGORIES),
                    "precio_eur": rng.randint(12, 950),
                    "peso_g": rng.randint(80, 9000),
                    "autonomia_h": rng.randint(2, 400),
                    "anio": rng.randint(2019, 2026),
                    "pais": rng.choice(vocabulary.COUNTRIES),
                    "garantia_meses": rng.choice([6, 12, 18, 24, 36]),
                }
            )
    return fichas, numbers


def main() -> None:
    rng = random.Random(SEED)  # noqa: S311 - reproducible corpus, not cryptography
    fichas, numbers = fichas_in_families(rng)
    fields = sorted(vocabulary.FIELDS)
    cases: list[dict[str, object]] = []

    for ficha, field in rng.sample([(f, k) for f in fichas for k in fields], MIX["lookup"]):
        cases.append(
            {
                "pregunta": vocabulary.FIELDS[field][0].format(name=ficha["nombre"]),
                "respuesta_referencia": str(ficha[field]),
                "refs": [ficha["id"]],
                "materia": field,
                "tipo": "positivo",
                "notas": "lookup",
            }
        )

    while sum(case["notas"] == "comparacion" for case in cases) < MIX["comparacion"]:
        a, b = rng.sample(fichas, 2)
        field = rng.choice(sorted(COMPARE))
        if a[field] == b[field] or str(a["nombre"]).split()[0] == str(b["nombre"]).split()[0]:
            continue  # no ties, and never two siblings: the question must have one answer
        winner, loser = (a, b) if a[field] > b[field] else (b, a)  # type: ignore[operator]
        cases.append(
            {
                "pregunta": COMPARE[field].format(a=a["nombre"], b=b["nombre"]),
                "respuesta_referencia": winner["nombre"],
                "refs": sorted([str(a["id"]), str(b["id"])]),
                "materia": field,
                "tipo": "positivo",
                "notas": "comparacion",
                "excluye": [loser["nombre"]],
            }
        )

    groups: dict[tuple[object, object, object], list[dict[str, object]]] = defaultdict(list)
    for ficha in fichas:
        groups[ficha["categoria"], ficha["pais"], ficha["anio"]].append(ficha)
    usable = [
        (key, members, field)
        for key, members in sorted(groups.items(), key=str)
        if 2 <= len(members) <= 3
        for field in sorted(FILTER)
        if len({m[field] for m in members}) == len(members)
    ]
    for (cat, pais, anio), members, field in rng.sample(usable, min(MIX["filtro"], len(usable))):
        winner = max(members, key=lambda m: m[field])  # type: ignore[arg-type,return-value]
        cases.append(
            {
                "pregunta": FILTER[field].format(cat=cat, pais=pais, anio=anio),
                "respuesta_referencia": winner["nombre"],
                "refs": sorted(str(m["id"]) for m in members),
                "materia": field,
                "tipo": "positivo",
                "notas": "filtro",
                "excluye": sorted(str(m["nombre"]) for m in members if m is not winner),
            }
        )
    n_filter = sum(case["notas"] == "filtro" for case in cases)

    for base in rng.sample(sorted(numbers), MIX["negativo-hermano"]):
        field = rng.choice(fields)
        cases.append(
            {
                "pregunta": vocabulary.FIELDS[field][0].format(name=f"{base} {numbers[base][SIBLINGS]}"),
                "respuesta_referencia": vocabulary.NOT_IN_CORPUS,
                "refs": [],
                "materia": field,
                "tipo": "negativo",
                "notas": "negativo-hermano",
            }
        )
    used = set(numbers)
    while sum(case["notas"] == "negativo" for case in cases) < MIX["negativo"]:
        base = "".join(rng.choice(vocabulary.SYLLABLES) for _ in range(3)).capitalize()
        if base in used:
            continue
        used.add(base)
        field = rng.choice(fields)
        cases.append(
            {
                "pregunta": vocabulary.FIELDS[field][0].format(name=f"{base} {rng.randint(100, 999)}"),
                "respuesta_referencia": vocabulary.NOT_IN_CORPUS,
                "refs": [],
                "materia": field,
                "tipo": "negativo",
                "notas": "negativo",
            }
        )

    rng.shuffle(cases)
    golden = [
        {
            "id": f"g2-{i:04d}",
            "version": 1,
            **case,
            "dificultad": DIFFICULTY[str(case["notas"])],
            "provenance": "sintetico_por_construccion",
        }
        for i, case in enumerate(cases)
    ]
    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("corpus.jsonl", fichas), ("questions.jsonl", golden)):
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")

    by_type: dict[bool, list[str]] = {True: [], False: []}
    for case in golden:
        by_type[case["tipo"] == "negativo"].append(str(case["id"]))
    share = len(by_type[True]) / len(golden)
    n_negative = round(N_CALIBRATION * share)
    calibration = sorted(
        rng.sample(by_type[True], n_negative) + rng.sample(by_type[False], N_CALIBRATION - n_negative)
    )
    digest = hashlib.sha256((OUT / "questions.jsonl").read_bytes()).hexdigest()
    (OUT / "calibracion.json").write_text(
        json.dumps({"golden_sha256": f"sha256:{digest}", "seed": SEED, "cases": calibration}, indent=2)
        + "\n",
        "utf-8",
    )
    kinds = {kind: sum(case["notas"] == kind for case in golden) for kind in MIX}
    print(
        f"{len(fichas)} fichas en {FAMILIES} familias, {len(golden)} casos {kinds} "
        f"({len(by_type[True])} negativos, {share:.0%}); filtro: {n_filter} de {MIX['filtro']} pedidos"
    )


if __name__ == "__main__":
    main()
