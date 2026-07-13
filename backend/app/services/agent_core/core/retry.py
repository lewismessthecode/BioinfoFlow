from __future__ import annotations

import asyncio
from dataclasses import dataclass
import math
from typing import Awaitable, Callable, TypeVar

from app.services.model_runtime.errors import ModelError


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
    return isinstance(exc, ModelError) and exc.retryable and exc.replay_safe


def retry_delay_for_error(
    exc: Exception,
    *,
    policy_delay_seconds: float,
    max_delay_seconds: float,
) -> float:
    cap = _finite_nonnegative(max_delay_seconds)
    policy_delay = min(_finite_nonnegative(policy_delay_seconds), cap)
    if not isinstance(exc, ModelError) or exc.retry_after_seconds is None:
        return policy_delay
    retry_after = exc.retry_after_seconds
    if not math.isfinite(retry_after) or retry_after < 0:
        return policy_delay
    return min(max(policy_delay, retry_after), cap)


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
            delay_seconds = retry_delay_for_error(
                exc,
                policy_delay_seconds=policy.delay_for_attempt(attempt),
                max_delay_seconds=policy.max_delay_seconds,
            )
            if on_retry is not None:
                await on_retry(attempt + 1, exc, delay_seconds)
            await asyncio.sleep(delay_seconds)
            attempt += 1


def _finite_nonnegative(value: float) -> float:
    return value if math.isfinite(value) and value >= 0 else 0.0
