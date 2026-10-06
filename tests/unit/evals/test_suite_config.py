"""R12: the judge is never the model that generates. This is the file RULES names.

A model grading its own output inflates faithfulness systematically: it agrees with itself. A suite that is
configured that way is refused before anything runs, with both names in the message.
"""

from typing import Any

import pytest

from evalgate.evals.prompts import Prompt
from evalgate.evals.suite import Suite, SuiteError, parse_suite

JUDGE = Prompt("judge_faithfulness", 1, "gemma4:12b-mlx", 0.0, "v1", "Eres un juez...\n", "a" * 64)
NODE: dict[str, Any] = {
    "suite": "rag-app",
    "golden": "evals/golden/rag-app-v1",
    "sut": {"model": "qwen3.5:9b-mlx", "outputs": "evals/suites/rag-app/sut/base.jsonl"},
    "judge": {"id": "faithfulness", "sampling": {"seed": 7, "max_tokens": 8}},
    "cache": "evals/suites/rag-app/cache.jsonl",
}


def test_a_valid_suite_takes_the_judges_model_and_temperature_from_its_prompt() -> None:
    suite = parse_suite(NODE, JUDGE)

    assert suite == Suite(
        name="rag-app",
        golden_dir="evals/golden/rag-app-v1",
        generator_model="qwen3.5:9b-mlx",
        judge_id="faithfulness",
        judge_prompt=JUDGE,
        # The temperature is the prompt's (it is in its frontmatter and in its digest): one source, not two.
        judge_sampling={"temperature": 0.0, "seed": 7, "max_tokens": 8},
        sut_outputs="evals/suites/rag-app/sut/base.jsonl",
        cache_path="evals/suites/rag-app/cache.jsonl",
        variants={"base": {}},
    )


def test_a_judge_that_is_the_generator_is_refused_with_both_names() -> None:
    same = {**NODE, "sut": {**NODE["sut"], "model": "gemma4:12b-mlx"}}

    with pytest.raises(SuiteError, match=r"gemma4:12b-mlx.*R12|R12.*gemma4:12b-mlx"):
        parse_suite(same, JUDGE)


@pytest.mark.parametrize("variant", ["GEMMA4:12B-MLX", " gemma4:12b-mlx "])
def test_writing_the_same_model_differently_does_not_get_past_the_rule(variant: str) -> None:
    with pytest.raises(SuiteError, match="R12"):
        parse_suite({**NODE, "sut": {**NODE["sut"], "model": variant}}, JUDGE)


def test_a_suite_that_sets_the_judges_temperature_twice_is_refused() -> None:
    """Two places to say it are two places to say it differently, and only one is in the prompt's digest."""
    twice = {**NODE, "judge": {"id": "faithfulness", "sampling": {"temperature": 0.7}}}

    with pytest.raises(SuiteError, match="temperature"):
        parse_suite(twice, JUDGE)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ({"suite": ""}, "suite"),
        ({"golden": None}, "golden"),
        ({"sut": {"outputs": "x"}}, "model"),
        ({"sut": {"model": "qwen3.5:9b-mlx"}}, "outputs"),
        ({"judge": {"sampling": {}}}, "id"),
        ({"cache": 3}, "cache"),
        ({"extra": True}, "extra"),
    ],
)
def test_a_suite_missing_what_it_needs_is_refused_naming_it(change: dict[str, Any], reason: str) -> None:
    with pytest.raises(SuiteError, match=reason):
        parse_suite({**NODE, **change}, JUDGE)


# --- variants of the system under test: the same suite, the system changed on purpose -----------------

VARIANTS: dict[str, Any] = {
    "base": {},
    "contexto-50": {"RAG_CONTEXT_KEEP": "0.5"},
    "modelo-pequeno": {"RAG_MODEL": "qwen3.5:4b-mlx"},
}


def test_a_suite_may_declare_variants_and_each_one_gets_its_own_recorded_outputs() -> None:
    suite = parse_suite({**NODE, "variants": VARIANTS}, JUDGE)

    assert suite is not None
    assert suite.variants == VARIANTS
    assert suite.outputs_of("contexto-50") == "evals/suites/rag-app/sut/contexto-50.jsonl"
    assert suite.outputs_of("base") == "evals/suites/rag-app/sut/base.jsonl"
    assert suite.model_of("modelo-pequeno") == "qwen3.5:4b-mlx"
    assert suite.model_of("contexto-50") == "qwen3.5:9b-mlx"


def test_a_suite_without_variants_has_only_the_base_one() -> None:
    suite = parse_suite(NODE, JUDGE)

    assert suite is not None
    assert suite.variants == {"base": {}}


def test_a_variant_that_makes_the_judge_generate_is_refused_like_the_suite_itself() -> None:
    """R12 cannot be walked around through a variant."""
    sneaky = {**VARIANTS, "juez-genera": {"RAG_MODEL": "gemma4:12b-mlx"}}

    with pytest.raises(SuiteError, match=r"juez-genera.*R12|R12.*juez-genera"):
        parse_suite({**NODE, "variants": sneaky}, JUDGE)


@pytest.mark.parametrize(
    ("variants", "reason"),
    [
        ({"contexto-50": {"RAG_CONTEXT_KEEP": "0.5"}}, "base"),
        ({"base": {"RAG_CONTEXT_KEEP": "0.5"}}, "base"),
        ({"base": {}, "x": {"RAG_CONTEXT_KEEP": 0.5}}, "x"),
        ({"base": {}, "../fuera": {}}, "fuera"),
        ({"base": {}, "x": {"PATH": "/tmp"}}, "PATH"),
    ],
)
def test_variants_that_are_not_what_they_claim_are_refused(variants: dict[str, Any], reason: str) -> None:
    """`base` must exist and change nothing; values are strings (they are environment variables); a name is
    a file name; and only the system's own knobs (RAG_*) may be set."""
    with pytest.raises(SuiteError, match=reason):
        parse_suite({**NODE, "variants": variants}, JUDGE)


def test_asking_for_a_variant_the_suite_does_not_declare_is_an_error() -> None:
    suite = parse_suite({**NODE, "variants": VARIANTS}, JUDGE)

    assert suite is not None
    with pytest.raises(SuiteError, match="inventada"):
        suite.outputs_of("inventada")
