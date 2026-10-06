"""Versioned prompts: `prompts/<id>.md` with mandatory frontmatter (RULES §2).

A prompt is never a string in the code. It is a file with an id, a version, the model and temperature it was
written for and a one-line note of what the version changed; every report records `{id, version, sha256}`
of each prompt it used (R14). That is what lets a change in a metric be traced to a change in a prompt,
which is half of what this project is for.

The digest is of the WHOLE file, frontmatter included: the temperature lives there, and two judges that
differ only in temperature are two judges.
"""

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_FENCE = "---\n"
_KEYS = {"id", "version", "modelo_destino", "temperatura", "cambios"}


class PromptError(ValueError):
    """A prompt file without the frontmatter that makes a metric change traceable to a prompt change."""


@dataclass(frozen=True, slots=True)
class Prompt:
    id: str
    version: int
    model: str  # `modelo_destino`
    temperature: float
    changes: str  # `cambios`: what this version changed, in one line
    body: str  # the text sent to the model, after the frontmatter
    sha256: str  # of the WHOLE file: frontmatter included, so nothing about it can change unseen


def _text(meta: dict[str, Any], key: str, filename: str) -> str:
    value = meta[key]
    if not isinstance(value, str) or not value.strip():
        raise PromptError(f"{filename}: {key} debe ser un texto no vacío")
    return value


def parse_prompt(text: str, filename: str) -> Prompt:
    """The prompt written in `text`, the content of a file called `filename`. Raises `PromptError`."""
    if not text.startswith(_FENCE) or _FENCE not in text[len(_FENCE) :]:
        raise PromptError(f"{filename}: sin frontmatter (RULES §2): el gate rechaza este prompt")
    header, body = text[len(_FENCE) :].split(_FENCE, maxsplit=1)
    meta = yaml.safe_load(header)
    if not isinstance(meta, dict):
        raise PromptError(f"{filename}: el frontmatter no es un mapping")
    if missing := sorted(_KEYS - meta.keys()):
        raise PromptError(f"{filename}: al frontmatter le falta {', '.join(missing)}")
    if extra := sorted(meta.keys() - _KEYS):
        raise PromptError(f"{filename}: campo de frontmatter no admitido: {', '.join(extra)}")

    version, temperature = meta["version"], meta["temperatura"]
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise PromptError(f"{filename}: version debe ser un entero >= 1, no {version!r}")
    if isinstance(temperature, bool) or not isinstance(temperature, int | float) or temperature < 0:
        raise PromptError(f"{filename}: temperatura debe ser un número >= 0, no {temperature!r}")
    prompt_id = _text(meta, "id", filename)
    if filename != f"{prompt_id}.md":
        raise PromptError(f"{filename}: el nombre del fichero no coincide con el id ({prompt_id})")
    if not body.strip():
        raise PromptError(f"{filename}: prompt vacío tras el frontmatter")
    return Prompt(
        id=prompt_id,
        version=version,
        model=_text(meta, "modelo_destino", filename),
        temperature=float(temperature),
        changes=_text(meta, "cambios", filename),
        body=body,
        sha256=hashlib.sha256(text.encode("utf-8")).hexdigest(),
    )


def load_prompt(path: Path) -> Prompt:
    """Read as bytes and decoded once, so the digest is of exactly what is on disk."""
    return parse_prompt(path.read_bytes().decode("utf-8"), path.name)
