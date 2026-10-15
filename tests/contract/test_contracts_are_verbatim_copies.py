"""R20: every file in docs/CONTRACTS/ is a verbatim copy of the version pinned in docs/spec/contracts.sha256.

A contract only changes as a versioned event: the new hash goes into the pin file in the same commit as its
CHANGELOG entry, so an edit that skips that step fails here.
"""

import hashlib
import re

import pytest

from ._paths import ROOT

LOCK = ROOT / "docs/spec/contracts.sha256"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _pinned() -> dict[str, str]:
    pinned: dict[str, str] = {}
    for line in LOCK.read_text(encoding="utf-8").splitlines():
        if line.strip() and not line.startswith("#"):
            digest, path = line.split(maxsplit=1)
            pinned[path] = digest
    return pinned


PINNED = _pinned()


@pytest.mark.parametrize("path", sorted(PINNED))
def test_contract_matches_pinned_hash(path: str) -> None:
    assert _sha256((ROOT / path).read_bytes()) == PINNED[path]


def test_every_contract_is_pinned() -> None:
    contracts = {str(p.relative_to(ROOT)) for p in (ROOT / "docs/CONTRACTS").iterdir() if p.is_file()}

    assert contracts == set(PINNED)


def test_every_pin_is_a_sha256_of_an_existing_file() -> None:
    malformed = [
        f"{path} {digest}"
        for path, digest in PINNED.items()
        if not re.fullmatch(r"[0-9a-f]{64}", digest) or not (ROOT / path).is_file()
    ]

    assert malformed == []
