"""Regenerate `evals/suites/compare-fixture/`: the reports `make eval-compare-twice` and the contract tests of
the gate compare. Deterministic (fixed seed): running it again writes the same bytes.

provenance: sintetico_declarado. No model produced these values. They are drawn so that the answer is known:

- `head-igual`:     the same values as base. The gate must pass, with every delta exactly 0.
- `head-ruido`:     each case re-drawn with the SAME underlying rates as base. Differences are noise.
- `head-regresion`: faithfulness loses 12 points and the hallucination rate goes from 2 % to 9 %. The gate
                    must block, and name those two metrics.

This is a fixture for the mechanics of `eval compare` and for G-DETERMINISM. It says nothing about how often
the gate is wrong: that is F7 (G-GATE-FP, G-GATE-MDE, G-GATE-POWER), measured on real model outputs.

Usage: python scripts/gen_compare_fixture.py
"""

import hashlib
import json
import random
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "evals" / "suites" / "compare-fixture"
N, SEED = 200, 20261006
# metric → probability that a case scores 1.0 in base. `alucinacion` is a rate where LOWER is better.
RATES = {
    "faithfulness": 0.88,
    "answer_relevancy": 0.90,
    "context_recall": 0.85,
    "citation_precision": 0.92,
    "alucinacion": 0.02,
    "respuesta_corta": 0.50,
}
REGRESSION = {"faithfulness": 0.76, "alucinacion": 0.09}
CASES = [f"cf-{i:04d}" for i in range(N)]


def draw(rng: random.Random, rates: dict[str, float]) -> dict[str, dict[str, float]]:
    return {metric: {case: float(rng.random() < rate) for case in CASES} for metric, rate in rates.items()}


def write(name: str, run: dict[str, dict[str, float]], dataset_sha: str) -> None:
    raw = OUT / name
    raw.mkdir(parents=True, exist_ok=True)
    metrics = []
    for metric, values in run.items():
        rows = [{"case_id": case, "value": values[case]} for case in CASES]
        (raw / f"{metric}.json").write_text(json.dumps(rows, separators=(",", ":")) + "\n", encoding="utf-8")
        metrics.append(
            {
                "id": metric,
                "value": sum(values.values()) / N,
                "n": N,
                "unit": "ratio",
                "raw_path": f"{name}/{metric}.json",
            }
        )
    report = {
        "contract_version": 1,
        "run_id": f"compare-fixture-{name}",
        "project": "evalgate",
        "suite": "compare-fixture",
        "created_at": "2026-10-06T00:00:00+00:00",
        "environment": {"hardware": "sintetico", "python": "3.12", "deterministic": True, "seed": SEED},
        "dataset": {"name": "compare-fixture", "version": 1, "n_cases": N, "sha256": dataset_sha},
        "metrics": metrics,
        "notes": "Informe sintético y declarado (scripts/gen_compare_fixture.py). Sin modelo detrás.",
    }
    (OUT / f"{name}.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cases = OUT / "cases.json"
    cases.write_text(json.dumps(CASES) + "\n", encoding="utf-8")
    dataset_sha = "sha256:" + hashlib.sha256(cases.read_bytes()).hexdigest()
    rng = random.Random(SEED)  # noqa: S311 - reproducible fixture, not cryptography
    base = draw(rng, RATES)
    write("base", base, dataset_sha)
    write("head-igual", base, dataset_sha)
    write("head-ruido", draw(rng, RATES), dataset_sha)
    write("head-regresion", draw(rng, {**RATES, **REGRESSION}), dataset_sha)
    (OUT / "gate.yaml").write_text(
        "# Reglas de la puerta para la suite sintética compare-fixture. Cinco métricas bloqueantes (más de\n"
        "# tres: la corrección de Holm es obligatoria) y una que solo informa.\n"
        "metrics:\n"
        "  - { id: faithfulness, blocking: true, absolute: 0.80 }\n"
        "  - { id: answer_relevancy, blocking: true }\n"
        "  - { id: context_recall, blocking: true }\n"
        "  - { id: citation_precision, blocking: true }\n"
        "  - { id: alucinacion, blocking: true, higher_is_better: false, absolute: 0.05 }\n"
        "  - { id: respuesta_corta, blocking: false }\n",
        encoding="utf-8",
    )
    (OUT / "expected.yaml").write_text(
        "# Lo que la puerta DEBE decidir sobre cada informe, escrito antes de ejecutarla.\n"
        "head-igual: pass\nhead-ruido: pass\nhead-regresion: block\n",
        encoding="utf-8",
    )
    print(f"escrito {OUT.relative_to(ROOT)}: base + 3 heads, {N} casos, {len(RATES)} métricas")


if __name__ == "__main__":
    main()
