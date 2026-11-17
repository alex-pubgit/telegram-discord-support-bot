"""Shared fixtures.

The suite must run with no network access, so every test runs behind a guard that
turns an accidental outbound connection into a loud failure. Loopback stays open
because the web simulator tests start a real server on 127.0.0.1.
"""

from __future__ import annotations

import socket
from typing import Any

import pytest

_LOOPBACK_HOSTS = frozenset({"127.0.0.1", "::1", "localhost"})
_real_connect = socket.socket.connect
_real_connect_ex = socket.socket.connect_ex
_real_getaddrinfo = socket.getaddrinfo


def _refuse_remote(host: object) -> None:
    if isinstance(host, bytes):
        host = host.decode("ascii", "replace")
    if host is not None and host not in _LOOPBACK_HOSTS:
        raise RuntimeError(
            f"A test tried to reach {host!r} over the network. The suite must stay offline."
        )


def _host_of(sock: socket.socket, address: Any) -> object:
    if sock.family in (socket.AF_INET, socket.AF_INET6) and isinstance(address, tuple):
        return address[0]
    return None


def _guarded_connect(sock: socket.socket, address: Any) -> None:
    _refuse_remote(_host_of(sock, address))
    return _real_connect(sock, address)


def _guarded_connect_ex(sock: socket.socket, address: Any) -> int:
    _refuse_remote(_host_of(sock, address))
    return _real_connect_ex(sock, address)


def _guarded_getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
    _refuse_remote(host)
    return _real_getaddrinfo(host, *args, **kwargs)


@pytest.fixture(autouse=True)
def _offline_only(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(socket.socket, "connect", _guarded_connect)
    monkeypatch.setattr(socket.socket, "connect_ex", _guarded_connect_ex)
    monkeypatch.setattr(socket, "getaddrinfo", _guarded_getaddrinfo)
