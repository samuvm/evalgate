"""Pinned external specifications: the OpenAI OpenAPI snapshot and the OTel semconv lock."""

import hashlib
import json
import re

from ._paths import ROOT


def _lock(path: str) -> dict[str, str]:
    fields: dict[str, str] = {}
    for line in (ROOT / path).read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            key, value = line.split(":", maxsplit=1)
            fields[key.strip()] = value.strip()
    return fields


def test_openapi_snapshot_matches_its_lock() -> None:
    lock = _lock("docs/spec/openai-openapi.lock")
    snapshot = (ROOT / lock["file"]).read_bytes()

    assert hashlib.sha256(snapshot).hexdigest() == lock["sha256"]
    assert re.fullmatch(r"[0-9a-f]{40}", lock["commit"])


def test_openapi_snapshot_describes_chat_completions() -> None:
    lock = _lock("docs/spec/openai-openapi.lock")
    spec = json.loads((ROOT / lock["file"]).read_text(encoding="utf-8"))

    assert spec["openapi"] == lock["openapi"]
    assert spec["info"]["version"] == lock["info_version"]
    assert "post" in spec["paths"]["/chat/completions"]
    schemas = spec["components"]["schemas"]
    assert {"CreateChatCompletionRequest", "CreateChatCompletionResponse"} <= schemas.keys()
    assert "CreateChatCompletionStreamResponse" in schemas


def test_otel_semconv_lock_pins_a_commit() -> None:
    lock = _lock("otel-semconv.lock")

    assert lock["repo"].startswith("open-telemetry/semantic-conventions")
    assert re.fullmatch(r"v\d+\.\d+\.\d+", lock["version"])
    assert re.fullmatch(r"[0-9a-f]{40}", lock["sha"])
