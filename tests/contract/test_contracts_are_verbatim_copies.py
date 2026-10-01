"""R20: docs/CONTRACTS/ (and the constitution and stack) are byte-for-byte copies of _comun/.

Two layers: docs/spec/copias-comun.sha256 pins the expected hash of every copy, so a clone without
_comun/ still detects an edited contract; when _comun/ is present, the copy is also compared against the
original, so a change in _comun/ that was not propagated is detected too.
"""

import hashlib

import pytest

from ._paths import COMUN, ROOT

LOCK = ROOT / "docs/spec/copias-comun.sha256"


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
def test_copy_matches_pinned_hash(path: str) -> None:
    assert _sha256((ROOT / path).read_bytes()) == PINNED[path]


@pytest.mark.parametrize("path", sorted(PINNED))
def test_copy_matches_comun_original(path: str) -> None:
    original = COMUN / path.removeprefix("docs/")
    if not COMUN.is_dir():
        # A published clone has no _comun/ (CONSTITUCION §7.8); the pinned hash above still guards it.
        return

    assert (ROOT / path).read_bytes() == original.read_bytes()


def test_every_contract_copy_is_pinned() -> None:
    copies = {str(p.relative_to(ROOT)) for p in (ROOT / "docs/CONTRACTS").iterdir() if p.is_file()}

    assert copies == {p for p in PINNED if p.startswith("docs/CONTRACTS/")}
