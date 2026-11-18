"""Per-member rate limiting with an in-memory token bucket."""

from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

# Buckets of members who have been idle long enough to be full again are dropped once
# the table grows past this size, so a busy community cannot grow it without bound.
MAX_TRACKED_MEMBERS = 10_000


@dataclass(frozen=True, slots=True)
class RateDecision:
    allowed: bool
    # True only for the first refused message of a burst. The bot tells the member once
    # and then stays quiet, so flooding the bot cannot make the bot flood the chat.
    notify: bool = False
    retry_after_seconds: int = 0


@dataclass(slots=True)
class _Bucket:
    tokens: float
    updated: float
    warned: bool = False


class RateLimiter:
    """Each member may send `burst` messages at once, then one every `refill_seconds`."""

    def __init__(
        self,
        burst: int,
        refill_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ):
        if burst < 1 or refill_seconds <= 0:
            raise ValueError("burst must be at least 1 and refill_seconds must be positive")
        self._burst = burst
        self._refill_seconds = refill_seconds
        self._clock = clock
        self._buckets: dict[str, _Bucket] = {}

    def check(self, member: str) -> RateDecision:
        """Spend one token for `member` if one is available."""
        now = self._clock()
        bucket = self._buckets.get(member)
        if bucket is None:
            self._forget_idle_members(now)
            bucket = self._buckets[member] = _Bucket(tokens=float(self._burst), updated=now)
        else:
            refilled = bucket.tokens + (now - bucket.updated) / self._refill_seconds
            bucket.tokens = min(float(self._burst), refilled)
            bucket.updated = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            bucket.warned = False
            return RateDecision(allowed=True)

        notify = not bucket.warned
        bucket.warned = True
        wait = math.ceil((1.0 - bucket.tokens) * self._refill_seconds)
        return RateDecision(allowed=False, notify=notify, retry_after_seconds=wait)

    def _forget_idle_members(self, now: float) -> None:
        if len(self._buckets) < MAX_TRACKED_MEMBERS:
            return
        full_after = self._burst * self._refill_seconds
        self._buckets = {
            member: bucket
            for member, bucket in self._buckets.items()
            if now - bucket.updated < full_after
        }
