"""The eval run: golden cases + what the system answered + a judge → the value of every metric per case.

Pure: the judge is a function handed in (R11), so nothing here knows whether its verdict came from a model,
from the recorded cache or from a test. What this module owns is WHICH cases each metric is scored over, and
that set is fixed by the golden set, never by the answers:

| metric                  | cases     | why |
|---|---|---|
| `answer_correct`        | all       | for a negative case the right answer is the abstention |
| `context_recall`        | positives | negatives stay out of the recall denominator (contract retrieval-metrics §2) |
| `abstencion_incorrecta` | positives | declining to answer what the corpus does contain |
| `faithfulness`          | all       | judged against the fichas the system itself retrieved |
| `juez_ilegible`         | all       | the judge did not give a verdict anyone can read |

Two runs of the same suite therefore always share their cases and the gate can pair them. A golden case with
no output, or an output for a case that does not exist, stops the run: scoring 199 of 200 and calling it the
suite is how a regression hides in the one case that crashed.
"""

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from evalgate.evals.metrics.answers import abstained, answer_correct, context_recall, faithful, unparseable


class RunError(ValueError):
    """The run cannot be scored as a whole: a case without an output, or data that contradicts itself."""


@dataclass(frozen=True, slots=True)
class GoldenCase:
    id: str
    question: str
    reference: str
    refs: tuple[str, ...]
    positive: bool
    # What a right answer must NOT name (`excluye` in the golden row): the other option of a comparison.
    excludes: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SutOutput:
    answer: str
    retrieved: tuple[str, ...]
    # The exact context the model received, when the system says so (a variant that cut it). `None`: the
    # model saw the retrieved fichas whole.
    context: str | None = None


Judge = Callable[[GoldenCase, SutOutput], str]  # returns the judge's verdict, as text
Scores = dict[str, dict[str, float]]  # metric → case → value


def golden_cases(rows: Sequence[Mapping[str, Any]]) -> list[GoldenCase]:
    """Golden rows (docs/CONTRACTS/retrieval-metrics.md §3) as cases. `refs` is empty iff the case is negative."""
    cases: list[GoldenCase] = []
    seen: set[str] = set()
    for row in rows:
        case = GoldenCase(
            str(row["id"]),
            str(row["pregunta"]),
            str(row["respuesta_referencia"]),
            tuple(row["refs"]),
            row["tipo"] == "positivo",
            tuple(row.get("excluye", ())),
        )
        if case.id in seen:
            raise RunError(f"caso {case.id} repetido en el golden set")
        if case.positive != bool(case.refs):
            raise RunError(f"caso {case.id}: `refs` debe estar vacío si y solo si el caso es negativo")
        seen.add(case.id)
        cases.append(case)
    return cases


def sut_outputs(rows: Sequence[Mapping[str, Any]]) -> dict[str, SutOutput]:
    """What the system under test printed, one row per case: `{id, retrieved, answer}`."""
    outputs: dict[str, SutOutput] = {}
    for row in rows:
        case_id = str(row["id"])
        if case_id in outputs:
            raise RunError(f"dos salidas del sistema para el caso {case_id}")
        context = row.get("context")
        outputs[case_id] = SutOutput(
            str(row["answer"]), tuple(row["retrieved"]), None if context is None else str(context)
        )
    return outputs


def evaluate(golden: Sequence[GoldenCase], outputs: Mapping[str, SutOutput], judge: Judge) -> Scores:
    """Score every case. The judge is asked exactly once per case, in golden order."""
    known = {case.id for case in golden}
    if missing := sorted(known - outputs.keys()):
        raise RunError(f"el sistema no respondió a {len(missing)} caso(s) del golden set: {', '.join(missing[:5])}")
    if unknown := sorted(outputs.keys() - known):
        raise RunError(f"salidas para casos que no están en el golden set: {', '.join(unknown[:5])}")

    scores: Scores = {
        "answer_correct": {},
        "context_recall": {},
        "abstencion_incorrecta": {},
        "faithfulness": {},
        "juez_ilegible": {},
    }
    for case in golden:
        output = outputs[case.id]
        scores["answer_correct"][case.id] = answer_correct(output.answer, case.reference, case.excludes)
        if case.positive:
            scores["context_recall"][case.id] = context_recall(output.retrieved, case.refs)
            scores["abstencion_incorrecta"][case.id] = abstained(output.answer)
        verdict = judge(case, output)
        scores["faithfulness"][case.id] = faithful(verdict)
        scores["juez_ilegible"][case.id] = unparseable(verdict)
    return scores


def judge_text(
    prompt_body: str, case: GoldenCase, output: SutOutput, fichas: Mapping[str, Mapping[str, Any]]
) -> str:
    """The exact text sent to the judge: its prompt, the fichas the SYSTEM retrieved, the question, the answer.

    The reference answer is never included: faithfulness is about what the answer claims against its own
    context, not about whether it is right (that is `answer_correct`, and it needs no judge).
    """
    if missing := [ficha_id for ficha_id in output.retrieved if ficha_id not in fichas]:
        raise RunError(f"caso {case.id}: el sistema recuperó fichas que no están en el corpus: {', '.join(missing)}")
    # What the model SAW. Judging against fichas it never read in full would call an honest abstention
    # unfaithful, and a degraded variant would look worse than it is for the wrong reason.
    context = output.context
    if context is None:
        context = "\n".join(json.dumps(fichas[ficha_id], ensure_ascii=False) for ficha_id in output.retrieved)
    return f"{prompt_body}\nFICHAS:\n{context}\n\nPREGUNTA: {case.question}\nRESPUESTA: {output.answer}\n"
