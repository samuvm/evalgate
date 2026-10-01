"""R15: zero network in unit tests. Unix sockets stay allowed: asyncio needs them for its self-pipe."""

from collections.abc import Iterator

import pytest
from pytest_socket import disable_socket, enable_socket


@pytest.fixture(autouse=True)
def _no_network() -> Iterator[None]:
    disable_socket(allow_unix_socket=True)
    yield
    enable_socket()
