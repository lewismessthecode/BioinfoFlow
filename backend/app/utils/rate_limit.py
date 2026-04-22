"""In-memory token bucket rate limiter for agent endpoints.

Limits per-user request rate to prevent LLM API credit runaway.
Uses a simple token bucket algorithm — no Redis needed for single-instance.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass, field


_BUCKET_TTL = 3600  # Evict buckets idle for 1 hour


@dataclass
class _Bucket:
    """Token bucket for a single user."""

    tokens: float = 10.0
    last_refill: float = field(default_factory=time.monotonic)


class RateLimiter:
    """In-memory per-user rate limiter using token bucket algorithm.

    Args:
        rate: Tokens added per second (e.g., 0.167 = 10/minute).
        burst: Maximum bucket capacity (allows bursts up to this many requests).
    """

    def __init__(self, rate: float = 10 / 60, burst: int = 10) -> None:
        self.rate = rate
        self.burst = burst
        self._buckets: dict[str, _Bucket] = defaultdict(lambda: _Bucket(tokens=burst))
        self._last_cleanup = time.monotonic()

    def _maybe_cleanup(self, now: float) -> None:
        """Periodically evict idle buckets to prevent unbounded growth."""
        if now - self._last_cleanup < _BUCKET_TTL:
            return
        self._last_cleanup = now
        stale = [uid for uid, b in self._buckets.items() if now - b.last_refill > _BUCKET_TTL]
        for uid in stale:
            del self._buckets[uid]

    def allow(self, user_id: str) -> tuple[bool, float]:
        """Check if a request from user_id should be allowed.

        Returns:
            (allowed, retry_after_seconds). If allowed is False,
            retry_after_seconds indicates when a token will be available.
        """
        now = time.monotonic()
        self._maybe_cleanup(now)
        bucket = self._buckets[user_id]
        elapsed = now - bucket.last_refill

        # Refill tokens
        bucket.tokens = min(self.burst, bucket.tokens + elapsed * self.rate)
        bucket.last_refill = now

        if bucket.tokens >= 1.0:
            bucket.tokens -= 1.0
            return True, 0.0

        # Calculate wait time until next token
        deficit = 1.0 - bucket.tokens
        retry_after = deficit / self.rate
        return False, retry_after

    def reset(self, user_id: str) -> None:
        """Reset a user's bucket (e.g., on plan upgrade)."""
        self._buckets.pop(user_id, None)


# Singleton — shared across all requests.
# Default: 10 requests/minute burst, refill at ~10/min steady state.
agent_rate_limiter = RateLimiter(rate=10 / 60, burst=10)
