"""Regenerate `evals/golden/rag-app-v1/`: the golden set of the `rag-app` suite. Deterministic (fixed seed).

provenance: sintetico_por_construccion (ADR-016). 120 fichas of products that do not exist and
200 questions about them; the right answer is known because it is generated together with the ficha. This
corpus does not measure the quality of any domain: it exists so the GATE can be measured (does it notice a
degradation, how often does it cry wolf), which is what this project is about.

Shape: docs/CONTRACTS/retrieval-metrics.md §3. One JSON object per line; `refs` are ficha ids, the stable
reference of this corpus. 15 % of the cases are negative (the product is not in the corpus and the right
answer is NO_CONSTA): the contract's floor, without which incorrect abstention cannot be measured.

Reuses the vocabulary of `examples/rag-app/generate_corpus.py` (loaded by path: examples/ is not a package)
so the golden set and the demo app speak about the same kind of ficha. No two questions ask the same field of
the same product.

Also writes `calibracion.json`: the 60-case subsuite (same 15 % of negatives) that F7 runs 50 times for the
false-positive matrix and that is labelled by hand for the judge's kappa.

Usage: python scripts/gen_golden.py
"""

import hashlib
import importlib.util
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "golden" / "rag-app-v1"
SEED, N_FICHAS, N_CASES, NEGATIVE_SHARE, N_CALIBRATION = 20261007, 120, 200, 0.15, 60

spec = importlib.util.spec_from_file_location(
    "generate_corpus", ROOT / "examples" / "rag-app" / "generate_corpus.py"
)
if spec is None or spec.loader is None:
    raise SystemExit("no se puede cargar examples/rag-app/generate_corpus.py")
corpus_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(corpus_module)


def main() -> None:
    fichas, _ = corpus_module.generate(N_FICHAS, 1, SEED)
    rng = random.Random(SEED + 1)  # noqa: S311 - reproducible corpus, not cryptography
    used = {str(ficha["nombre"]) for ficha in fichas}
    n_negative = round(N_CASES * NEGATIVE_SHARE)
    fields = sorted(corpus_module.FIELDS)
    pairs = rng.sample([(ficha, field) for ficha in fichas for field in fields], N_CASES - n_negative)

    cases: list[dict[str, object]] = []
    for ficha, field in pairs:
        question, _presentation = corpus_module.FIELDS[field]
        cases.append(
            {
                "pregunta": question.format(name=ficha["nombre"]),
                # The DATUM, not its presentation ("433", not "433 €"). The question already names the unit
                # ("precio en euros", "en gramos"), so a system that answers "433" is right. With the unit in
                # the reference, the first real run scored 0.39 on a system that was answering correctly
                # (2026-10-07): the measure was wrong, not the system.
                "respuesta_referencia": str(ficha[field]),
                "refs": [ficha["id"]],
                "materia": field,
                "tipo": "positivo",
            }
        )
    for _ in range(n_negative):
        field = rng.choice(fields)
        cases.append(
            {
                "pregunta": corpus_module.FIELDS[field][0].format(name=corpus_module.model_name(rng, used)),
                "respuesta_referencia": corpus_module.NOT_IN_CORPUS,
                "refs": [],
                "materia": field,
                "tipo": "negativo",
            }
        )
    rng.shuffle(cases)
    golden = [
        {
            "id": f"gs-{i:04d}",
            "version": 1,
            **case,
            "dificultad": "facil",
            "provenance": "sintetico_por_construccion",
            "notas": "",
        }
        for i, case in enumerate(cases)
    ]

    OUT.mkdir(parents=True, exist_ok=True)
    for name, rows in (("corpus.jsonl", fichas), ("questions.jsonl", golden)):
        (OUT / name).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), "utf-8")

    negatives = [case["id"] for case in golden if case["tipo"] == "negativo"]
    positives = [case["id"] for case in golden if case["tipo"] == "positivo"]
    n_cal_negative = round(N_CALIBRATION * NEGATIVE_SHARE)
    calibration = sorted(
        rng.sample(negatives, n_cal_negative) + rng.sample(positives, N_CALIBRATION - n_cal_negative)
    )
    digest = hashlib.sha256((OUT / "questions.jsonl").read_bytes()).hexdigest()
    (OUT / "calibracion.json").write_text(
        json.dumps({"golden_sha256": f"sha256:{digest}", "seed": SEED, "cases": calibration}, indent=2)
        + "\n",
        "utf-8",
    )
    print(
        f"{len(fichas)} fichas, {len(golden)} casos ({len(negatives)} negativos), "
        f"{len(calibration)} de calibración -> {OUT.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
