"""G-CACHE-INVAL: the cache key of the judges invalidates exactly what it must. The command of the goal.

"Aquí es donde están los bugs de una caché, no en el hit rate" (docs/GOALS.yaml). A key that forgets a
component serves a stale judgement after the judge changed (a metric that silently stops measuring the
current prompt); a key that includes something irrelevant never hits (a cost that silently never goes down).
Both are checked component by component, and the goal's number is the share of those checks that hold.
"""

from dataclasses import fields, replace
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from tests._meter import Meter

from evalgate.evals.cache.key import ModelCall, cache_key, text_digest

GOAL = "G-CACHE-INVAL"
BASE = ModelCall(
    role="judge",
    caller_id="faithfulness",
    model="gemma4:12b-mlx",
    sampling={"temperature": 0.0, "seed": 7},
    prompt_version=3,
    prompt_sha256=text_digest("Eres un juez de fidelidad..."),
    text_sha256=text_digest("respuesta a juzgar"),
)
# One changed value per component of R10: judge id, model, sampling parameters, prompt version, prompt
# sha256 and sha256 of the evaluated text. Plus the role, which this project adds (ADR-015).
CHANGED: dict[str, Any] = {
    "role": "generator",
    "caller_id": "relevancia",
    "model": "gemma4:26b-mlx",
    "sampling": {"temperature": 0.2, "seed": 7},
    "prompt_version": 4,
    "prompt_sha256": text_digest("Eres un juez de fidelidad. Sé estricto."),
    "text_sha256": text_digest("otra respuesta a juzgar"),
}


def test_every_field_of_a_call_is_a_component_someone_decided_about() -> None:
    """A field added to ModelCall and forgotten here would be a component nobody checked."""
    assert {field.name for field in fields(ModelCall)} == set(CHANGED)


@pytest.mark.parametrize("component", sorted(CHANGED))
def test_changing_any_one_component_changes_the_key(component: str, meter: Meter) -> None:
    changed = cache_key(replace(BASE, **{component: CHANGED[component]}))

    holds = changed != cache_key(BASE)
    meter.check(GOAL, holds)
    assert holds, f"cambiar {component} no invalida la entrada"


def test_changing_nothing_keeps_the_key(meter: Meter) -> None:
    same = ModelCall(**{field.name: getattr(BASE, field.name) for field in fields(ModelCall)})

    holds = cache_key(same) == cache_key(BASE)
    meter.check(GOAL, holds)
    assert holds


def test_the_order_sampling_parameters_are_written_in_is_not_a_component(meter: Meter) -> None:
    reordered = replace(BASE, sampling={"seed": 7, "temperature": 0.0})

    holds = cache_key(reordered) == cache_key(BASE)
    meter.check(GOAL, holds)
    assert holds


def test_a_sampling_parameter_added_changes_the_key(meter: Meter) -> None:
    """`max_tokens` cuts the answer short: with it, it is another call."""
    holds = cache_key(replace(BASE, sampling={**BASE.sampling, "max_tokens": 64})) != cache_key(BASE)
    meter.check(GOAL, holds)
    assert holds


def test_zero_point_zero_and_zero_are_the_same_temperature(meter: Meter) -> None:
    """A YAML that says `temperature: 0` and one that says `0.0` ask the model for the same thing."""
    holds = cache_key(replace(BASE, sampling={"temperature": 0, "seed": 7})) == cache_key(BASE)
    meter.check(GOAL, holds)
    assert holds


def test_components_cannot_bleed_into_each_other(meter: Meter) -> None:
    """The classic bug of a key built by concatenation: ("ab", "c") and ("a", "bc") give the same string."""
    one = replace(BASE, caller_id="ab", model="c")
    other = replace(BASE, caller_id="a", model="bc")

    holds = cache_key(one) != cache_key(other)
    meter.check(GOAL, holds)
    assert holds


def test_bumping_one_judges_prompt_invalidates_all_of_its_entries_and_none_of_the_others(
    meter: Meter,
) -> None:
    """The sentence of the goal, literally: 100 % of THAT judge's entries, 0 % of the rest."""
    texts = [text_digest(f"respuesta {i}") for i in range(50)]
    other_judge = replace(BASE, caller_id="relevancia", prompt_sha256=text_digest("otro prompt"))
    cached = {cache_key(replace(judge, text_sha256=t)) for judge in (BASE, other_judge) for t in texts}

    bumped = replace(BASE, prompt_version=4, prompt_sha256=text_digest("Eres un juez de fidelidad. v4"))
    own_hits = sum(cache_key(replace(bumped, text_sha256=t)) in cached for t in texts)
    others_hits = sum(cache_key(replace(other_judge, text_sha256=t)) in cached for t in texts)

    holds = (own_hits, others_hits) == (0, len(texts))
    meter.check(GOAL, holds)
    assert holds


def test_the_text_digest_is_of_the_exact_text() -> None:
    assert text_digest("a") == text_digest("a")
    assert text_digest("a") != text_digest("a ")
    assert text_digest("á") != text_digest("a")
    assert len(text_digest("")) == 64


def test_the_key_is_a_sha256_and_does_not_contain_what_it_was_made_from() -> None:
    key = cache_key(BASE)

    assert len(key) == 64
    assert int(key, 16) >= 0
    assert "gemma" not in key


CALLS = st.builds(
    ModelCall,
    role=st.sampled_from(["judge", "generator"]),
    caller_id=st.text(min_size=1, max_size=12),
    model=st.text(min_size=1, max_size=12),
    sampling=st.dictionaries(
        st.sampled_from(["temperature", "seed", "max_tokens", "top_p"]),
        st.integers(0, 100) | st.floats(0, 2, allow_nan=False) | st.text(max_size=5),
        max_size=4,
    ),
    prompt_version=st.integers(1, 50),
    prompt_sha256=st.text("0123456789abcdef", min_size=64, max_size=64),
    text_sha256=st.text("0123456789abcdef", min_size=64, max_size=64),
)


def _same(one: ModelCall, other: ModelCall) -> bool:
    def sampling(call: ModelCall) -> list[tuple[str, object]]:
        return sorted(
            (name, float(v) if isinstance(v, int | float) and not isinstance(v, bool) else str(v))
            for name, v in call.sampling.items()
        )

    return replace(one, sampling={}) == replace(other, sampling={}) and sampling(one) == sampling(other)


@given(CALLS, CALLS)
def test_two_calls_share_a_key_exactly_when_they_are_the_same_call(
    meter: Meter, one: ModelCall, other: ModelCall
) -> None:
    holds = (cache_key(one) == cache_key(other)) == _same(one, other)
    meter.check(GOAL, holds)
    assert holds


@given(CALLS)
def test_a_call_always_has_its_own_key(meter: Meter, call: ModelCall) -> None:
    holds = cache_key(call) == cache_key(replace(call, sampling=dict(reversed(list(call.sampling.items())))))
    meter.check(GOAL, holds)
    assert holds
