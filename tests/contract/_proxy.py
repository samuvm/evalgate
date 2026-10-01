"""Drive the real proxy app against an in-memory upstream (httpx.MockTransport). No sockets, no Ollama."""

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from functools import cache
from typing import Any

import httpx
from fastapi.testclient import TestClient
from jsonschema import Draft202012Validator

from evalgate.proxy.app import ProxySettings, create_app
from evalgate.proxy.streaming import UsageRecord

from ._paths import ROOT

FIXTURES = ROOT / "tests" / "fixtures" / "openai"
UPSTREAM = "http://upstream.test/v1"


def fixture(name: str) -> bytes:
    return (FIXTURES / name).read_bytes()


@dataclass
class Upstream:
    """Records what the proxy sent and answers with a canned response (or raises)."""

    status: int = 200
    body: bytes = b"{}"
    # A list of pairs, not a mapping: a canned upstream must be able to repeat a field (two `Set-Cookie`).
    headers: dict[str, str] | list[tuple[str, str]] = field(
        default_factory=lambda: {"content-type": "application/json"}
    )
    error: Exception | None = None
    received: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.received.append(request)
        if self.error is not None:
            raise self.error
        return httpx.Response(self.status, content=self.body, headers=self.headers)


def proxy(
    upstream: Upstream,
    *,
    normalize: bool = False,
    on_usage: Callable[[UsageRecord], None] | None = None,
) -> TestClient:
    client = httpx.AsyncClient(transport=httpx.MockTransport(upstream.handler))
    settings = ProxySettings(upstream_base_url=UPSTREAM, normalize=normalize, on_usage=on_usage)
    return TestClient(create_app(settings, client=client))


def honour_nullable(node: Any) -> Any:
    """Translate the OpenAPI **3.0** keyword `nullable: true` into what OpenAPI **3.1** means by it.

    The pinned snapshot declares `openapi: 3.1.0` and still carries `nullable: true` in 111 places, which is
    a 3.0 keyword: in 3.1 nullability is a type union, and **no JSON Schema validator honours `nullable`**.
    Validating the snapshot literally rejects `"finish_reason": null`, which is what OpenAI's own streaming
    protocol sends in every chunk but the last. So it is not the provider that fails the contract, it is the
    contract that contradicts itself, and the intent is unambiguous: the field admits null.

    The translation widens `type` and, when there is one, the `enum` — nothing else. It can only ACCEPT what
    the vendor already declared nullable; it never relaxes a field the vendor did not. ADR-011.
    """
    if isinstance(node, dict):
        widened = {key: honour_nullable(value) for key, value in node.items()}
        if widened.pop("nullable", None) is True:
            if "type" in widened:
                kind = widened["type"]
                widened["type"] = [*kind, "null"] if isinstance(kind, list) else [kind, "null"]
            if "enum" in widened and None not in widened["enum"]:
                widened["enum"] = [*widened["enum"], None]
        return widened
    if isinstance(node, list):
        return [honour_nullable(item) for item in node]
    return node


@cache
def _spec() -> dict[str, Any]:
    spec: dict[str, Any] = json.loads((ROOT / "docs/spec/openai-openapi-2.3.0.json").read_text("utf-8"))
    return spec


@cache
def _components() -> dict[str, Any]:
    components: dict[str, Any] = honour_nullable(_spec()["components"])
    return components


def openai_validator(component: str) -> Callable[[Any], list[str]]:
    """Validator for one component of the pinned OpenAPI snapshot. Returns the error messages."""
    validator = Draft202012Validator(
        {"$ref": f"#/components/schemas/{component}", "components": _components()}
    )
    return lambda document: [f"{list(e.path)}: {e.message}" for e in validator.iter_errors(document)]


def sse_events(raw: bytes) -> list[dict[str, Any]]:
    """The JSON chunks of an SSE response: comments, keep-alives and `[DONE]` are not chunks."""
    events: list[dict[str, Any]] = []
    for frame in [piece for piece in raw.split(b"\n\n") if piece]:
        for line in frame.split(b"\n"):
            if not line.startswith(b"data:"):
                continue
            payload = line[len(b"data:") :].strip()
            if payload and payload != b"[DONE]":
                events.append(json.loads(payload))
    return events
