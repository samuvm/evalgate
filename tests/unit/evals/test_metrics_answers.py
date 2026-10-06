"""Every metric with made-up inputs whose result is worked out by hand (PROJECT §4, nivel 1).

All of them are per-case and return 0.0 or 1.0 (or a fraction, for recall): the gate resamples CASES, so a
metric that only existed as an aggregate could not be compared at all.
"""

import pytest

from evalgate.evals.metrics.answers import ABSTENTION, abstained, answer_correct, context_recall, faithful, unparseable


@pytest.mark.parametrize(
    ("answer", "reference", "correct"),
    [
        ("6 meses", "6 meses", 1.0),
        ("El Midemi-977 tiene 6 meses de garantía.", "6 meses", 1.0),
        ("Tiene 16 meses de garantía.", "6 meses", 0.0),  # 16 is not 6: tokens, never substrings
        ("Tiene 6 meses, o quizá 60 meses.", "6 meses", 1.0),
        ("Se fabrica en NORUEGA.", "Noruega", 1.0),
        ("Se fabrica en Suecia.", "Noruega", 0.0),
        ("Pesa 6073 g.", "6073 g", 1.0),
        ("Pesa 6.073 g.", "6073 g", 0.0),  # another number as written; the metric does not guess formats
        ("Cuesta 911 €", "911 €", 1.0),
        ("Cuesta 911 euros", "911 €", 0.0),  # the unit is part of the reference
        ("2020", "2020", 1.0),
        ("Fue fabricado en el año 2020.", "2020", 1.0),
        ("En 12020 unidades", "2020", 0.0),
        ("La lámpara de cultivo es de Kenia", "kenia", 1.0),
        ("", "6 meses", 0.0),
        ("meses 6", "6 meses", 0.0),  # the reference's words, in the reference's order
    ],
)
def test_an_answer_is_correct_when_it_contains_the_reference_as_whole_words(
    answer: str, reference: str, correct: float
) -> None:
    assert answer_correct(answer, reference) == correct


@pytest.mark.parametrize(
    ("answer", "correct"),
    [
        ("NO_CONSTA", 1.0),
        ("no_consta", 1.0),
        ("La respuesta es NO_CONSTA.", 1.0),
        ("No consta en las fichas.", 0.0),  # the system was told the exact word; paraphrase is not it
        ("El Zzz-000 pesa 300 g.", 0.0),
    ],
)
def test_for_a_question_with_no_answer_in_the_corpus_the_correct_answer_is_the_abstention(
    answer: str, correct: float
) -> None:
    assert answer_correct(answer, ABSTENTION) == correct


def test_accents_and_case_do_not_make_an_answer_wrong() -> None:
    assert answer_correct("Se fabricó en PERÚ", "Perú") == 1.0
    assert answer_correct("Se fabrico en Peru", "Perú") == 1.0


def test_an_empty_reference_is_a_broken_case_not_a_free_point() -> None:
    with pytest.raises(ValueError, match="reference"):
        answer_correct("cualquier cosa", "  ")


@pytest.mark.parametrize(
    ("retrieved", "relevant", "recall"),
    [
        (["ficha-0001", "ficha-0002", "ficha-0003"], ["ficha-0002"], 1.0),
        (["ficha-0001", "ficha-0003"], ["ficha-0002"], 0.0),
        (["ficha-0001", "ficha-0002"], ["ficha-0002", "ficha-0009"], 0.5),
        ([], ["ficha-0002"], 0.0),
        (["ficha-0002", "ficha-0002"], ["ficha-0002"], 1.0),  # repeats do not count twice: sets (contract §2)
    ],
)
def test_context_recall_is_the_share_of_relevant_references_that_were_retrieved(
    retrieved: list[str], relevant: list[str], recall: float
) -> None:
    """recall@k = |R ∩ P_k| / |R| (docs/CONTRACTS/retrieval-metrics.md §2)."""
    assert context_recall(retrieved, relevant) == recall


def test_context_recall_of_a_case_with_nothing_relevant_is_not_defined() -> None:
    """Contract §2: negative cases stay OUT of the denominator. The caller leaves them out; asking is a bug."""
    with pytest.raises(ValueError, match="relevant"):
        context_recall(["ficha-0001"], [])


@pytest.mark.parametrize(("answer", "value"), [("NO_CONSTA", 1.0), ("Es no_consta.", 1.0), ("6 meses", 0.0), ("", 0.0)])
def test_abstained_says_whether_the_system_declined_to_answer(answer: str, value: float) -> None:
    assert abstained(answer) == value


@pytest.mark.parametrize(
    ("verdict", "is_faithful", "is_unparseable"),
    [
        ("FIEL", 1.0, 0.0),
        ("fiel", 1.0, 0.0),
        ("FIEL.", 1.0, 0.0),
        ("NO_FIEL", 0.0, 0.0),
        ("NO_FIEL: inventa el precio.", 0.0, 0.0),
        ("Veredicto: FIEL", 1.0, 0.0),
        ("Creo que podría ser correcto", 0.0, 1.0),
        ("", 0.0, 1.0),
        ("FIEL o NO_FIEL, no lo sé", 0.0, 1.0),  # both words: the judge did not decide
    ],
)
def test_the_judges_verdict_is_read_strictly_and_what_cannot_be_read_is_counted_apart(
    verdict: str, is_faithful: float, is_unparseable: float
) -> None:
    """A verdict nobody can read is NOT faithful (the metric must not be inflated by a rambling judge), and
    it is also reported on its own, so a judge that stops following its format shows up as that."""
    assert (faithful(verdict), unparseable(verdict)) == (is_faithful, is_unparseable)
