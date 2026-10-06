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
