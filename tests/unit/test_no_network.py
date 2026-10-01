"""R15 is a mechanism, not a convention: an INET socket opened from a unit test must fail."""

import socket

import pytest
from pytest_socket import SocketBlockedError


@pytest.mark.filterwarnings("ignore:A test tried to use socket.socket:UserWarning")
def test_inet_socket_is_blocked_in_unit_tests() -> None:
    with pytest.raises(SocketBlockedError):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
