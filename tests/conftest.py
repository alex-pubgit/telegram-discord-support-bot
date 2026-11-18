"""Shared fixtures.

The suite must run with no network access, so every test runs behind a guard that
turns an accidental outbound connection into a loud failure. Loopback stays open
because the web simulator tests start a real server on 127.0.0.1.
"""

from __future__ import annotations

import socket
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from supportbot.answer import KnowledgeBaseBackend
from supportbot.brain import SupportBrain
from supportbot.guardrails.ratelimit import RateLimiter
from supportbot.kb import Retriever, load_knowledge_base
from supportbot.storage import Store

SAMPLE_KB = Path(__file__).resolve().parent.parent / "sample_kb"

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


class FakeClock:
    """A clock the test moves by hand. Serves the rate limiter and the store."""

    def __init__(self) -> None:
        self._now = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)

    def advance(self, seconds: float) -> None:
        self._now += timedelta(seconds=seconds)

    def monotonic(self) -> float:
        return self._now.timestamp()

    def now(self) -> datetime:
        return self._now


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(clock: FakeClock) -> Store:
    return Store(":memory:", salt="test-salt", clock=clock.now)


@pytest.fixture(scope="session")
def sample_backend() -> KnowledgeBaseBackend:
    return KnowledgeBaseBackend(Retriever(load_knowledge_base(SAMPLE_KB)))


@pytest.fixture
def brain(sample_backend: KnowledgeBaseBackend, store: Store, clock: FakeClock) -> SupportBrain:
    """The bot over the sample knowledge base: 3 messages at once, then one every 20 seconds."""
    return SupportBrain(sample_backend, store, RateLimiter(3, 20.0, clock=clock.monotonic))
