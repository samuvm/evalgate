"""An eval suite: its golden set, the system under test, the judge and the rules that make it valid.

The rule that matters here is R12: **the judge is never the model that generates.** A model grading its own
output agrees with itself, and faithfulness goes up for a reason that has nothing to do with quality. A
suite configured that way is refused before a single model is called.

The judge's model and temperature are not in the suite file at all: they are the prompt's (its frontmatter,
and so its digest). One place to say it, and it is the place the cache key reads.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from evalgate.evals.prompts import Prompt

_KEYS = {"suite", "golden", "sut", "judge", "cache"}


class SuiteError(ValueError):
    """A suite that would measure something meaningless. Refused before a single model is called."""


@dataclass(frozen=True, slots=True)
class Suite:
    name: str
    golden_dir: str
    generator_model: str
    judge_id: str
    judge_prompt: Prompt
    judge_sampling: Mapping[str, float | int | str]
    sut_outputs: str
    cache_path: str


def _text(node: Mapping[str, Any], key: str, where: str) -> str:
    value = node.get(key)
    if not isinstance(value, str) or not value.strip():
        raise SuiteError(f"{where}: falta `{key}` o no es un texto")
    return value


def parse_suite(node: Mapping[str, Any], judge_prompt: Prompt) -> Suite:
    """Build the suite or raise `SuiteError` naming what is wrong."""
    if extra := sorted(node.keys() - _KEYS):
        raise SuiteError(f"suite: campo no admitido {', '.join(extra)}")
    name = _text(node, "suite", "suite")
    golden = _text(node, "golden", name)
    cache = _text(node, "cache", name)
    sut, judge = node.get("sut"), node.get("judge")
    if not isinstance(sut, Mapping) or not isinstance(judge, Mapping):
        raise SuiteError(f"{name}: `sut` y `judge` deben ser bloques con sus campos (model, outputs, id)")
    generator = _text(sut, "model", f"{name} sut")
    outputs = _text(sut, "outputs", f"{name} sut")
    judge_id = _text(judge, "id", f"{name} judge")

    if generator.strip().lower() == judge_prompt.model.strip().lower():
        raise SuiteError(
            f"{name}: el juez ({judge_prompt.model}) es el mismo modelo que genera ({generator}). "
            "Un modelo que juzga su propia salida infla la métrica (R12)."
        )
    sampling = judge.get("sampling", {})
    if not isinstance(sampling, Mapping):
        raise SuiteError(f"{name} judge: `sampling` debe ser un bloque")
    if "temperature" in sampling:
        raise SuiteError(
            f"{name} judge: la temperature del juez es la de su prompt ({judge_prompt.temperature}); "
            "aquí no se repite"
        )
    return Suite(
        name=name,
        golden_dir=golden,
        generator_model=generator,
        judge_id=judge_id,
        judge_prompt=judge_prompt,
        judge_sampling={"temperature": judge_prompt.temperature, **sampling},
        sut_outputs=outputs,
        cache_path=cache,
    )
