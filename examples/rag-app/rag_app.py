"""Minimal RAG app: lexical retrieval over the synthetic fichas + one chat completion per question.

It is a CLIENT of any OpenAI-compatible endpoint. Adopting evalgate costs one environment variable:

    OPENAI_BASE_URL=http://localhost:11434/v1  python rag_app.py   # straight to Ollama
    OPENAI_BASE_URL=http://localhost:8080/v1   python rag_app.py   # through the evalgate proxy

Standard library only, and never imports evalgate (RULES R13): if it did, "zero code" adoption would be a lie.
Prints one JSON line per question: {"id", "retrieved", "answer"}.
"""

import argparse
import json
import os
import random
import re
import unicodedata
import urllib.request
from pathlib import Path

# RAG_DATA points the app at another corpus (the eval suite uses the 200-case golden set). Default: its own.
DATA = Path(os.environ.get("RAG_DATA", Path(__file__).parent / "data"))
TOP_K = 3
SYSTEM = (
    "Responde solo con el dato pedido, usando únicamente las fichas. "
    "Si el producto no aparece en las fichas, responde exactamente: NO_CONSTA."
)


STOPWORDS = {"el", "la", "los", "las", "de", "del", "en", "que", "se", "y", "a", "un", "una", "tiene", "es"}


def tokens(text: str) -> set[str]:
    plain = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode()
    return set(re.findall(r"[a-z0-9]+(?:-[0-9]+)?", plain)) - STOPWORDS


def ficha_tokens(ficha: dict[str, object]) -> set[str]:
    """Only the values: field names appear in every ficha and would make every score tie."""
    return tokens(" ".join(str(value) for key, value in ficha.items() if key != "id"))


def load(name: str) -> list[dict[str, object]]:
    with (DATA / name).open(encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def retrieve(question: str, fichas: list[dict[str, object]]) -> list[dict[str, object]]:
    """Top-k fichas by token overlap with the question; ties broken by id, so it is deterministic."""
    query = tokens(question)
    scored = sorted(fichas, key=lambda f: (-len(query & ficha_tokens(f)), str(f["id"])))
    return scored[:TOP_K]


def degraded(
    question_id: str, context: list[dict[str, object]], fichas: list[dict[str, object]]
) -> list[dict[str, object]]:
    """RAG_RANDOM_DOCS=p: each retrieved ficha is swapped for a random one with probability p. Seeded by the
    question, so a run is reproducible. Default 0: nothing changes."""
    share = float(os.environ.get("RAG_RANDOM_DOCS", "0"))
    if share <= 0:
        return context
    rng = random.Random(f"{question_id}:{share}")  # noqa: S311 - reproducible degradation, not cryptography
    return [rng.choice(fichas) if rng.random() < share else ficha for ficha in context]


def context_text(context: list[dict[str, object]]) -> str:
    """RAG_CONTEXT_KEEP=f: only the first fraction f of the context text reaches the model. Default 1."""
    text = "\n".join(json.dumps(f, ensure_ascii=False) for f in context)
    return text[: int(len(text) * float(os.environ.get("RAG_CONTEXT_KEEP", "1")))]


def ask(base_url: str, model: str, question: str, fichas: str) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"Fichas:\n{fichas}\n\nPregunta: {question}"},
        ],
        "temperature": float(os.environ.get("RAG_TEMPERATURE", "0")),
        # RAG_SEED only matters above temperature 0: it is what makes two runs of the same system differ.
        "seed": int(os.environ.get("RAG_SEED", "7")),
        "max_tokens": 64,
        # qwen3.5 reasons by default and spends max_tokens on it (measured 2026-09-10).
        "reasoning_effort": "none",
    }
    request = urllib.request.Request(  # noqa: S310 - the URL is the app's own configuration
        f"{base_url.rstrip('/')}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {os.environ.get('OPENAI_API_KEY', 'local')}",
        },
    )
    with urllib.request.urlopen(request, timeout=600) as response:  # noqa: S310
        body = json.load(response)
    return str(body["choices"][0]["message"]["content"]).strip()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=None, help="Only the first N questions.")
    args = parser.parse_args()
    base_url = os.environ.get("OPENAI_BASE_URL", "http://localhost:11434/v1")
    model = os.environ.get("RAG_MODEL", "qwen3.5:9b-mlx")
    fichas = load("corpus.jsonl")
    for question in load("questions.jsonl")[: args.limit]:
        context = degraded(str(question["id"]), retrieve(str(question["pregunta"]), fichas), fichas)
        shown = context_text(context)
        answer = ask(base_url, model, str(question["pregunta"]), shown)
        row = {"id": question["id"], "retrieved": [f["id"] for f in context], "answer": answer}
        if "RAG_CONTEXT_KEEP" in os.environ:
            # What the model actually saw, when it is not simply the retrieved fichas: whoever judges the
            # answer has to judge it against this, not against fichas the model never read in full.
            row["context"] = shown
        print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
