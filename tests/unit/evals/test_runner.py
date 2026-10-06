"""The run, with a judge that is a plain function: what gets scored, over which cases, and what is refused.

No model is called here (R11): the judge is injected, and in these tests it is a lambda.
"""

from typing import Any

import pytest

from evalgate.evals.cache.cached import CacheMiss, cached_answer
from evalgate.evals.cache.key import ModelCall, cache_key
from evalgate.evals.cache.store import Entry, ModelCache
from evalgate.evals.runner import GoldenCase, RunError, SutOutput, evaluate, golden_cases, judge_text, sut_outputs

ROWS: list[dict[str, Any]] = [
    {"id": "gs-1", "pregunta": "¿Garantía del Alfa-1?", "respuesta_referencia": "6 meses", "refs": ["f-1"], "tipo": "positivo"},
    {"id": "gs-2", "pregunta": "¿País del Beta-2?", "respuesta_referencia": "Noruega", "refs": ["f-2"], "tipo": "positivo"},
    {"id": "gs-3", "pregunta": "¿Peso del Nada-0?", "respuesta_referencia": "NO_CONSTA", "refs": [], "tipo": "negativo"},
]
OUTPUTS: list[dict[str, Any]] = [
    {"id": "gs-1", "retrieved": ["f-1", "f-9"], "answer": "Tiene 6 meses."},
    {"id": "gs-2", "retrieved": ["f-8", "f-9"], "answer": "NO_CONSTA"},
    {"id": "gs-3", "retrieved": ["f-7"], "answer": "Pesa 300 g."},
]


def always(verdict: str) -> Any:
    return lambda case, output: verdict


def test_golden_rows_become_cases_and_the_contract_between_type_and_refs_is_enforced() -> None:
    cases = golden_cases(ROWS)

    assert cases[0] == GoldenCase("gs-1", "¿Garantía del Alfa-1?", "6 meses", ("f-1",), positive=True)
    assert (cases[2].positive, cases[2].refs) == (False, ())
    with pytest.raises(RunError, match="gs-9"):
        golden_cases([{**ROWS[0], "id": "gs-9", "refs": []}])  # positive without refs (contract §3)
    with pytest.raises(RunError, match="gs-9"):
        golden_cases([{**ROWS[2], "id": "gs-9", "refs": ["f-1"]}])  # negative with refs
    with pytest.raises(RunError, match="gs-1"):
        golden_cases([ROWS[0], ROWS[0]])  # the same id twice


def test_every_metric_is_scored_over_cases_fixed_by_the_golden_set() -> None:
    scores = evaluate(golden_cases(ROWS), sut_outputs(OUTPUTS), always("FIEL"))

    # gs-1 right; gs-2 abstained wrongly; gs-3 answered where it should have abstained.
    assert scores["answer_correct"] == {"gs-1": 1.0, "gs-2": 0.0, "gs-3": 0.0}
    # Only positives: negative cases stay out of the recall denominator (contract §2).
    assert scores["context_recall"] == {"gs-1": 1.0, "gs-2": 0.0}
    assert scores["abstencion_incorrecta"] == {"gs-1": 0.0, "gs-2": 1.0}
    assert scores["faithfulness"] == {"gs-1": 1.0, "gs-2": 1.0, "gs-3": 1.0}
    assert scores["juez_ilegible"] == {"gs-1": 0.0, "gs-2": 0.0, "gs-3": 0.0}


def test_the_case_sets_do_not_depend_on_what_the_system_answered() -> None:
    """Otherwise two runs could not be paired: the gate would refuse to compare them (CaseMismatch)."""
    other = [{**row, "answer": "NO_CONSTA", "retrieved": []} for row in OUTPUTS]

    one = evaluate(golden_cases(ROWS), sut_outputs(OUTPUTS), always("FIEL"))
    two = evaluate(golden_cases(ROWS), sut_outputs(other), always("no sé"))

    assert {metric: set(cases) for metric, cases in one.items()} == {m: set(c) for m, c in two.items()}


def test_the_judge_is_asked_once_per_case_and_its_verdict_feeds_two_metrics() -> None:
    asked: list[str] = []

    def judge(case: GoldenCase, output: SutOutput) -> str:
        asked.append(case.id)
        return {"gs-1": "FIEL", "gs-2": "NO_FIEL", "gs-3": "mmm, depende"}[case.id]

    scores = evaluate(golden_cases(ROWS), sut_outputs(OUTPUTS), judge)

    assert asked == ["gs-1", "gs-2", "gs-3"]
    assert scores["faithfulness"] == {"gs-1": 1.0, "gs-2": 0.0, "gs-3": 0.0}
    assert scores["juez_ilegible"] == {"gs-1": 0.0, "gs-2": 0.0, "gs-3": 1.0}


def test_a_golden_case_the_system_never_answered_stops_the_run() -> None:
    """Scoring 199 of 200 and calling it the suite is how a regression hides in the case that crashed."""
    with pytest.raises(RunError, match="gs-3"):
        evaluate(golden_cases(ROWS), sut_outputs(OUTPUTS[:2]), always("FIEL"))


def test_an_output_for_a_case_that_is_not_in_the_golden_set_stops_the_run() -> None:
    with pytest.raises(RunError, match="gs-99"):
        evaluate(golden_cases(ROWS), sut_outputs([*OUTPUTS, {"id": "gs-99", "retrieved": [], "answer": "x"}]), always("FIEL"))


def test_the_same_output_twice_is_refused() -> None:
    with pytest.raises(RunError, match="gs-1"):
        sut_outputs([OUTPUTS[0], OUTPUTS[0]])


def test_the_text_the_judge_reads_has_the_prompt_the_retrieved_fichas_the_question_and_the_answer() -> None:
    fichas = {"f-1": {"id": "f-1", "nombre": "Alfa-1", "garantia_meses": 6}, "f-9": {"id": "f-9", "nombre": "Otro"}}
    case, output = golden_cases(ROWS)[0], sut_outputs(OUTPUTS)["gs-1"]

    text = judge_text("PROMPT DEL JUEZ\n", case, output, fichas)

    assert text.startswith("PROMPT DEL JUEZ\n")
    assert '"nombre": "Alfa-1"' in text
    assert '"nombre": "Otro"' in text
    assert "PREGUNTA: ¿Garantía del Alfa-1?" in text
    assert text.rstrip().endswith("RESPUESTA: Tiene 6 meses.")
    assert "6 meses\n" not in text.replace("Tiene 6 meses.", ""), "the reference answer is never shown to the judge"


def test_a_retrieved_ficha_that_is_not_in_the_corpus_is_a_broken_run() -> None:
    case, output = golden_cases(ROWS)[0], sut_outputs(OUTPUTS)["gs-1"]

    with pytest.raises(RunError, match="f-9"):
        judge_text("P\n", case, output, {"f-1": {"id": "f-1"}})


# --- answering from the recorded cache -------------------------------------------------------------

CALL = ModelCall("judge", "faithfulness", "gemma4:12b-mlx", {"temperature": 0.0}, 1, "p" * 64, "t" * 64)


def test_a_recorded_answer_is_returned_without_making_the_call(tmp_path: Any) -> None:
    cache = ModelCache(tmp_path / "c.jsonl")
    cache.put(Entry(cache_key(CALL), "FIEL", 100, 1))

    def never() -> tuple[str, int, int]:
        raise AssertionError("the model was called on a cache hit")

    assert cached_answer(ModelCache(tmp_path / "c.jsonl"), CALL, never) == "FIEL"


def test_a_miss_makes_the_call_once_and_records_it(tmp_path: Any) -> None:
    made: list[int] = []

    def live() -> tuple[str, int, int]:
        made.append(1)
        return "NO_FIEL", 120, 2

    cache = ModelCache(tmp_path / "c.jsonl")

    assert cached_answer(cache, CALL, live) == "NO_FIEL"
    assert cached_answer(cache, CALL, live) == "NO_FIEL"
    assert len(made) == 1
    assert ModelCache(tmp_path / "c.jsonl").get(cache_key(CALL)) == Entry(cache_key(CALL), "NO_FIEL", 120, 2)


def test_a_miss_in_a_recorded_run_is_an_error_and_no_model_is_called(tmp_path: Any) -> None:
    """`make eval` runs in the gate and never calls a model. A miss there means the cache and the suite
    drifted apart, and the answer is `make eval-refresh`, said out loud."""
    with pytest.raises(CacheMiss, match="eval-refresh"):
        cached_answer(ModelCache(tmp_path / "c.jsonl"), CALL, None)
