from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable, TypeVar


ResultT = TypeVar("ResultT")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    base_delay_seconds: float = 0.25
    max_delay_seconds: float = 2.0

    def delay_for_attempt(self, attempt_number: int) -> float:
        exponent = max(attempt_number - 1, 0)
        delay = self.base_delay_seconds * (2**exponent)
        return min(delay, self.max_delay_seconds)


DEFAULT_RETRY_POLICY = RetryPolicy()


def is_retryable_model_error(exc: Exception) -> bool:
    message = str(exc).lower()
    name = exc.__class__.__name__.lower()
    if any(token in name for token in ("timeout", "ratelimit", "connection", "apierror")):
        return True
    return any(
        token in message
        for token in (
            "timeout",
            "timed out",
            "rate limit",
            "too many requests",
            "429",
            "502",
            "503",
            "504",
            "temporarily unavailable",
            "connection reset",
            "connection aborted",
            "connection refused",
        )
    )


async def run_with_retry(
    operation: Callable[[], Awaitable[ResultT]],
    *,
    policy: RetryPolicy = DEFAULT_RETRY_POLICY,
    should_retry: Callable[[Exception], bool] = is_retryable_model_error,
    on_retry: Callable[[int, Exception, float], Awaitable[None]] | None = None,
) -> ResultT:
    attempt = 1
    while True:
        try:
            return await operation()
        except Exception as exc:
            if attempt >= policy.max_attempts or not should_retry(exc):
                raise
            delay_seconds = policy.delay_for_attempt(attempt)
            if on_retry is not None:
                await on_retry(attempt + 1, exc, delay_seconds)
            await asyncio.sleep(delay_seconds)
            attempt += 1
