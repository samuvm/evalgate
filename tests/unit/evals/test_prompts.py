"""Prompts are versioned files, never strings in the code (RULES §2).

What is tested is the envelope —the frontmatter that lets a report say which prompt, which version, which
bytes— and never the wording: a test that asserts the exact text of a prompt only says the file did not
change, breaks every time the prompt improves and gets deleted within two weeks (RULES §2).
"""

import hashlib
from pathlib import Path

import pytest

from evalgate.evals.prompts import Prompt, PromptError, load_prompt, parse_prompt

GOOD = """\
---
id: judge_faithfulness
version: 3
modelo_destino: gemma4:12b-mlx
temperatura: 0.0
cambios: "v3: se pide una sola palabra"
---
Eres un juez.

Responde FIEL o NO_FIEL.
"""


def test_a_prompt_file_becomes_its_metadata_its_body_and_the_digest_of_the_whole_file() -> None:
    prompt = parse_prompt(GOOD, "judge_faithfulness.md")

    assert prompt == Prompt(
        id="judge_faithfulness",
        version=3,
        model="gemma4:12b-mlx",
        temperature=0.0,
        changes="v3: se pide una sola palabra",
        body="Eres un juez.\n\nResponde FIEL o NO_FIEL.\n",
        sha256=hashlib.sha256(GOOD.encode("utf-8")).hexdigest(),
    )


def test_changing_only_the_frontmatter_changes_the_digest() -> None:
    """The temperature is in the frontmatter. A digest of the body alone would call two different judges
    the same prompt."""
    hotter = GOOD.replace("temperatura: 0.0", "temperatura: 0.7")

    one, other = parse_prompt(GOOD, "judge_faithfulness.md"), parse_prompt(hotter, "judge_faithfulness.md")

    assert one is not None
    assert other is not None
    assert (one.body, one.sha256 != other.sha256) == (other.body, True)


@pytest.mark.parametrize(
    ("text", "reason"),
    [
        ("Eres un juez.\n", "frontmatter"),
        ("---\nid: x\n", "frontmatter"),
        (GOOD.replace("version: 3\n", ""), "version"),
        (GOOD.replace("modelo_destino: gemma4:12b-mlx\n", ""), "modelo_destino"),
        (GOOD.replace("temperatura: 0.0\n", ""), "temperatura"),
        (GOOD.replace('cambios: "v3: se pide una sola palabra"\n', ""), "cambios"),
        (GOOD.replace("version: 3", "version: tres"), "version"),
        (GOOD.replace("version: 3", "version: 0"), "version"),
        (GOOD.replace("temperatura: 0.0", "temperatura: tibia"), "temperatura"),
        (GOOD.replace("version: 3", "version: 3\nautor: yo"), "autor"),
        (GOOD.replace("Eres un juez.\n\nResponde FIEL o NO_FIEL.\n", "\n"), "vacío"),
        ("---\n- una\n- lista\n---\ntexto\n", "frontmatter"),
    ],
)
def test_a_prompt_without_its_full_frontmatter_is_refused_naming_what_is_missing(text: str, reason: str) -> None:
    with pytest.raises(PromptError, match=reason):
        parse_prompt(text, "judge_faithfulness.md")


def test_the_file_name_is_the_prompt_id_or_it_is_refused() -> None:
    with pytest.raises(PromptError, match=r"otro\.md"):
        parse_prompt(GOOD, "otro.md")


def test_load_reads_the_file_as_bytes_so_the_digest_is_of_what_is_on_disk(tmp_path: Path) -> None:
    path = tmp_path / "judge_faithfulness.md"
    path.write_bytes(GOOD.encode("utf-8"))

    prompt = load_prompt(path)

    assert prompt is not None
    assert prompt.sha256 == hashlib.sha256(path.read_bytes()).hexdigest()
    assert prompt.id == "judge_faithfulness"


def test_every_prompt_in_the_repository_loads(tmp_path: Path) -> None:
    """The envelope of the real files, not their wording."""
    root = Path(__file__).resolve().parents[3] / "prompts"
    found = sorted(root.glob("*.md"))

    assert found, "prompts/ no tiene ningún prompt"
    for path in found:
        prompt = load_prompt(path)
        assert prompt is not None
        assert prompt.id == path.stem
