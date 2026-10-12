"""`evalgate meta kappa`: the judge against the human labels (G-JUDGE-KAPPA). I/O and wiring only (RULES §2).

What is measured is the judge OF THE SUITE: the same prompt, sampling and recorded cache that produce the
suite's `faithfulness`, asked about the very text each labelled item was built from. So the kappa published
is the kappa of the number published, not of a judge set up apart for the occasion.

Which batches count is not an argument of the command: it is written in `<labels>/kappa.yaml`, next to the
labels, so the choice is versioned and cannot be made after looking at the result. Batches listed under
`development` were used to build the judge; their agreement is reported apart and is
never the number of the goal.

Like `eval run`, a recorded run never calls a model: a verdict that is not in the cache is an error unless
`--refresh`.
"""

import hashlib
import json
from pathlib import Path
from typing import Any

import yaml

from evalgate.evals.cache.cached import cached_answer
from evalgate.evals.cache.key import ModelCall, text_digest
from evalgate.evals.cache.store import ModelCache
from evalgate.evals.judges import client
from evalgate.evals.metrics.agreement import agreement_block, judge_label
from evalgate.evals.prompts import load_prompt
from evalgate.evals.runner import golden_cases, judge_text, sut_outputs
from evalgate.evals.suite import parse_suite
from evalgate.gate.config import gate_config

JUDGE_PROMPT = Path("prompts/judge_faithfulness.md")
HUMAN_LABELS = {"FIEL", "NO_FIEL"}


class LabelsError(ValueError):
    """The labels, the items they were given on and the suite no longer describe the same thing."""


def _jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise LabelsError(f"no existe {path}")
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _shown_digest(context: str, question: str, answer: str) -> str:
    """The digest `scripts/prepare_labels.py` gave the item: of exactly what the labeller was shown."""
    shown = {"contexto": context, "pregunta": question, "respuesta": answer}
    return (
        "sha256:" + hashlib.sha256(json.dumps(shown, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    )


def run(  # noqa: PLR0913 - wiring: every name is a file or a knob of the run
    labels_dir: Path, root: Path, goals_path: Path, out: Path, *, refresh: bool, base_url: str
) -> dict[str, Any]:
    """Measure, merge the result into the meta-eval document at `out` and return the document."""
    plan = yaml.safe_load((labels_dir / "kappa.yaml").read_text("utf-8"))
    suite_dir = root / "evals" / "suites" / str(plan["suite"])
    prompt = load_prompt(root / JUDGE_PROMPT)
    suite = parse_suite(yaml.safe_load((suite_dir / "suite.yaml").read_text("utf-8")), prompt)
    golden = {case.id: case for case in golden_cases(_jsonl(root / suite.golden_dir / "questions.jsonl"))}
    fichas = {str(row["id"]): row for row in _jsonl(root / suite.golden_dir / "corpus.jsonl")}
    cache = ModelCache(root / suite.cache_path)
    comparacion = yaml.safe_load(goals_path.read_text("utf-8"))["comparacion"]
    # The interval uses the gate's own replicates, seed and level: one place decides them (GOALS.yaml).
    config = gate_config(comparacion, yaml.safe_load((suite_dir / "gate.yaml").read_text("utf-8"))["metrics"])
    outputs: dict[str, Any] = {}

    def ratings_of(batch: int) -> dict[str, tuple[str, str]]:
        human = {str(row["item_id"]): row for row in _jsonl(labels_dir / f"tanda-{batch}.labels.jsonl")}
        ratings: dict[str, tuple[str, str]] = {}
        for key in _jsonl(labels_dir / f"tanda-{batch}.key.jsonl"):
            item_id, variant, case_id = str(key["item_id"]), str(key["variant"]), str(key["case_id"])
            if item_id not in human:
                raise LabelsError(f"tanda {batch}: {item_id} está sin etiquetar; la tanda se mide entera")
            label = human[item_id]
            if label["label"] not in HUMAN_LABELS or label["item_sha256"] != key["item_sha256"]:
                raise LabelsError(f"tanda {batch}: la etiqueta de {item_id} no corresponde a su ítem")
            if variant not in outputs:
                outputs[variant] = sut_outputs(_jsonl(root / suite.outputs_of(variant)))
            case, output = golden[case_id], outputs[variant][case_id]
            text = judge_text(prompt.body, case, output, fichas)
            context = text.split("\nFICHAS:\n", 1)[1].split("\n\nPREGUNTA: ", 1)[0]
            if _shown_digest(context, case.question, output.answer) != key["item_sha256"]:
                raise LabelsError(
                    f"tanda {batch}: {item_id} ({variant} {case_id}) ya no es lo que se etiquetó: "
                    "las salidas grabadas del sistema han cambiado"
                )
            call = ModelCall(
                "judge",
                suite.judge_id,
                prompt.model,
                suite.judge_sampling,
                prompt.version,
                prompt.sha256,
                text_digest(text),
            )
            live = None
            if refresh:
                live = lambda text=text: client.chat(base_url, prompt.model, text, suite.judge_sampling)  # noqa: E731
            ratings[item_id] = (str(label["label"]), judge_label(cached_answer(cache, call, live)))
        return ratings

    def block(batches: list[int]) -> dict[str, Any]:
        ratings: dict[str, tuple[str, str]] = {}
        for batch in batches:
            ratings.update(ratings_of(batch))
        measured = agreement_block(
            ratings, replicates=config.replicates, seed=config.seed, level=config.policy.level
        )
        return {**measured, "batches": batches}

    measurement, development = list(plan["measurement"]), list(plan.get("development", []))
    if set(measurement) & set(development):
        raise LabelsError("kappa.yaml: una tanda no puede ser a la vez de desarrollo y de medida")
    kappa = block(measurement)
    document: dict[str, Any] = json.loads(out.read_text("utf-8")) if out.exists() else {}
    document["cohens_kappa"] = {
        **kappa,
        "suite": suite.name,
        "judge": {
            "prompt_id": prompt.id,
            "prompt_version": prompt.version,
            "prompt_sha256": "sha256:" + prompt.sha256,
            "model": prompt.model,
            "sampling": dict(suite.judge_sampling),
        },
        "labelled_by": "samuel",
        # Batches the judge was built against. Reported so nobody mistakes them for the measurement.
        "development": block(development) if development else None,
    }
    document["n_etiquetados"] = kappa["n"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n", "utf-8")
    return document
