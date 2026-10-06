"""An eval suite: its golden set, the system under test, the judge and the rules that make it valid.

The rule that matters here is R12: **the judge is never the model that generates.** A model grading its own
output agrees with itself, and faithfulness goes up for a reason that has nothing to do with quality. A
suite configured that way is refused before a single model is called.

The judge's model and temperature are not in the suite file at all: they are the prompt's (its frontmatter,
and so its digest). One place to say it, and it is the place the cache key reads.
"""

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Any

from evalgate.evals.prompts import Prompt

_KEYS = {"suite", "golden", "sut", "judge", "cache", "variants"}
BASE = "base"  # the variant that changes nothing: the system as it is
_KNOB = re.compile(r"^RAG_[A-Z_]+$")  # a variant may only turn the system's own knobs
_NAME = re.compile(r"^[a-z0-9][a-z0-9.-]*$")  # it becomes a file name


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
    # Variants of the system under test: name → the environment variables that change it. `base` is the
    # system as it is. The same suite, the same judge, the system degraded on purpose: what the gate is
    # measured against.
    variants: Mapping[str, Mapping[str, str]]

    def _known(self, variant: str) -> Mapping[str, str]:
        if variant not in self.variants:
            raise SuiteError(f"{self.name}: la suite no declara la variante {variant!r}")
        return self.variants[variant]

    def outputs_of(self, variant: str) -> str:
        """Where the recorded outputs of `variant` live: next to the base ones, under the variant's name."""
        self._known(variant)
        return str(PurePosixPath(self.sut_outputs).with_name(f"{variant}.jsonl"))

    def model_of(self, variant: str) -> str:
        return self._known(variant).get("RAG_MODEL", self.generator_model)


def _variants(node: Any, name: str, generator: str, judge_model: str) -> dict[str, dict[str, str]]:
    if node is None:
        return {BASE: {}}
    if not isinstance(node, Mapping) or node.get(BASE) != {}:
        raise SuiteError(f"{name}: `variants` debe incluir `{BASE}: {{}}`, la variante que no cambia nada")
    parsed: dict[str, dict[str, str]] = {}
    for variant, knobs in node.items():
        if not isinstance(variant, str) or not _NAME.match(variant):
            raise SuiteError(f"{name}: nombre de variante no válido: {variant!r}")
        if not isinstance(knobs, Mapping):
            raise SuiteError(f"{name}: la variante {variant} debe ser un bloque de variables")
        for key, value in knobs.items():
            if not isinstance(key, str) or not _KNOB.match(key):
                raise SuiteError(f"{name}: la variante {variant} toca {key!r}; solo se admiten variables RAG_*")
            if not isinstance(value, str):
                raise SuiteError(f"{name}: la variante {variant}: {key} debe ser un texto (es una variable de entorno)")
        model = str(knobs.get("RAG_MODEL", generator))
        if model.strip().lower() == judge_model.strip().lower():
            raise SuiteError(f"{name}: en la variante {variant} el juez ({judge_model}) sería el que genera (R12)")
        parsed[variant] = dict(knobs)
    return parsed


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
        variants=_variants(node.get("variants"), name, generator, judge_prompt.model),
    )
