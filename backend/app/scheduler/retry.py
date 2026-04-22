from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class RetryPolicy:
    max_retries: int = 0
    delay_seconds: float = 30
    backoff_multiplier: float = 2.0
    max_delay_seconds: float = 600
    retry_on: list[str] = field(default_factory=list)

    @classmethod
    def from_raw(cls, value: dict[str, Any] | None) -> "RetryPolicy":
        raw = dict(value or {})
        retry_on = raw.get("retry_on")
        return cls(
            max_retries=max(0, int(raw.get("max_retries", 0) or 0)),
            delay_seconds=max(0.0, float(raw.get("delay_seconds", 30) or 0)),
            backoff_multiplier=max(
                1.0, float(raw.get("backoff_multiplier", 2.0) or 1.0)
            ),
            max_delay_seconds=max(0.0, float(raw.get("max_delay_seconds", 600) or 0)),
            retry_on=[
                str(pattern).strip()
                for pattern in (retry_on if isinstance(retry_on, list) else [])
                if str(pattern).strip()
            ],
        )


RETRY_DEFAULT_BIO = RetryPolicy(
    max_retries=2,
    delay_seconds=60,
    retry_on=["connection", "oom", "137", "killed"],
)


class RetryEvaluator:
    def should_retry(
        self,
        task: Any,
        error: str,
        *,
        retry_policy: dict[str, Any] | None = None,
    ) -> bool:
        if int(getattr(task, "attempt", 1) or 1) >= int(
            getattr(task, "max_attempts", 1) or 1
        ):
            return False
        policy = self._parse_policy(task, retry_policy=retry_policy)
        patterns = [pattern.lower() for pattern in policy.retry_on]
        if not patterns:
            return True
        message = (error or "").lower()
        return any(pattern in message for pattern in patterns)

    def next_delay(
        self,
        task: Any,
        *,
        retry_policy: dict[str, Any] | None = None,
    ) -> float:
        policy = self._parse_policy(task, retry_policy=retry_policy)
        attempt = max(1, int(getattr(task, "attempt", 1) or 1))
        delay = policy.delay_seconds * (policy.backoff_multiplier ** (attempt - 1))
        return min(delay, policy.max_delay_seconds)

    def is_oom_error(self, error: str) -> bool:
        message = (error or "").lower()
        return any(
            pattern in message
            for pattern in ["out of memory", "oom", "137", "killed", "cannot allocate"]
        )

    def _parse_policy(
        self,
        task: Any,
        *,
        retry_policy: dict[str, Any] | None = None,
    ) -> RetryPolicy:
        raw = (
            retry_policy
            if retry_policy is not None
            else getattr(task, "retry_policy", None)
        )
        return RetryPolicy.from_raw(raw)
