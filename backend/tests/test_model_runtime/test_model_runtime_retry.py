"""Regression tests for AgentCore-owned model retry policy."""

from __future__ import annotations

import asyncio

import pytest

from app.services.agent_core.core.retry import (
    RetryPolicy,
    is_retryable_model_error,
    retry_delay_for_error,
    run_with_retry,
)
from app.services.model_runtime.errors import ModelError


@pytest.mark.parametrize(
    ("category", "http_status"),
    [
        ("rate_limit", 429),
        ("timeout", None),
        ("connection", None),
        ("service_unavailable", 502),
        ("service_unavailable", 503),
        ("service_unavailable", 504),
    ],
)
def test_structured_transient_replay_safe_errors_are_retryable(
    category: str,
    http_status: int | None,
) -> None:
    error = ModelError(
        category=category,  # type: ignore[arg-type]
        message="Safe provider failure.",
        http_status=http_status,
        retryable=True,
        replay_safe=True,
    )

    assert is_retryable_model_error(error) is True


@pytest.mark.parametrize("http_status", [400, 401, 403])
def test_structured_client_errors_are_not_retryable(http_status: int) -> None:
    error = ModelError(
        category="invalid_request" if http_status == 400 else "authentication",
        message="The request cannot be retried.",
        http_status=http_status,
        retryable=False,
    )

    assert is_retryable_model_error(error) is False


def test_retry_requires_replay_safety_even_for_transient_errors() -> None:
    error = ModelError(
        category="timeout",
        message="The result may already have been committed.",
        retryable=True,
        replay_safe=False,
    )

    assert is_retryable_model_error(error) is False


def test_unstructured_exception_text_never_drives_retry_policy() -> None:
    error = RuntimeError("429 timeout connection reset temporarily unavailable")

    assert is_retryable_model_error(error) is False


def test_retry_after_is_honored_without_shortening_policy_backoff() -> None:
    error = ModelError(
        category="rate_limit",
        message="Rate limited.",
        http_status=429,
        retryable=True,
        retry_after_seconds=1.5,
    )

    assert retry_delay_for_error(
        error,
        policy_delay_seconds=0.25,
        max_delay_seconds=2.0,
    ) == 1.5
    assert retry_delay_for_error(
        error,
        policy_delay_seconds=1.75,
        max_delay_seconds=2.0,
    ) == 1.75


@pytest.mark.parametrize(
    ("retry_after", "policy_delay", "expected"),
    [
        (3600.0, 0.25, 2.0),
        (float("inf"), 0.25, 0.25),
        (float("nan"), 0.25, 0.25),
        (-10.0, 0.25, 0.25),
        (-10.0, -1.0, 0.0),
    ],
)
def test_retry_after_is_finite_nonnegative_and_capped_by_policy(
    retry_after: float,
    policy_delay: float,
    expected: float,
) -> None:
    error = ModelError(
        category="rate_limit",
        message="Rate limited.",
        retryable=True,
        retry_after_seconds=retry_after,
    )

    assert retry_delay_for_error(
        error,
        policy_delay_seconds=policy_delay,
        max_delay_seconds=2.0,
    ) == expected


@pytest.mark.asyncio
async def test_run_with_retry_uses_structured_retry_after_and_safe_callback(
    monkeypatch,
) -> None:
    secret = "sentinel-provider-secret"
    attempts = 0
    sleeps: list[float] = []
    callbacks: list[tuple[int, str, float]] = []

    async def operation() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise ModelError(
                category="rate_limit",
                message="The provider rate limit was exceeded.",
                http_status=429,
                retryable=True,
                retry_after_seconds=1.25,
                cause=RuntimeError(f"Authorization: Bearer {secret}"),
            )
        return "ok"

    async def fake_sleep(delay: float) -> None:
        sleeps.append(delay)

    async def on_retry(next_attempt: int, error: Exception, delay: float) -> None:
        callbacks.append((next_attempt, str(error), delay))

    monkeypatch.setattr("app.services.agent_core.core.retry.asyncio.sleep", fake_sleep)

    result = await run_with_retry(
        operation,
        policy=RetryPolicy(max_attempts=2, base_delay_seconds=0.1),
        on_retry=on_retry,
    )

    assert result == "ok"
    assert attempts == 2
    assert sleeps == [1.25]
    assert callbacks == [(2, "The provider rate limit was exceeded.", 1.25)]
    assert secret not in repr(callbacks)


@pytest.mark.asyncio
async def test_retry_budget_is_exhausted_before_error_reaches_fallback_caller(
    monkeypatch,
) -> None:
    order: list[str] = []

    async def primary() -> None:
        order.append("primary")
        raise ModelError(
            category="service_unavailable",
            message="Provider unavailable.",
            http_status=503,
            retryable=True,
        )

    async def fake_sleep(delay: float) -> None:
        del delay

    monkeypatch.setattr("app.services.agent_core.core.retry.asyncio.sleep", fake_sleep)

    with pytest.raises(ModelError):
        await run_with_retry(primary, policy=RetryPolicy(max_attempts=3))
    order.append("fallback")

    assert order == ["primary", "primary", "primary", "fallback"]


@pytest.mark.asyncio
async def test_cancellation_propagates_without_retry(monkeypatch) -> None:
    attempts = 0
    slept = False

    async def operation() -> None:
        nonlocal attempts
        attempts += 1
        raise asyncio.CancelledError

    async def fake_sleep(delay: float) -> None:
        nonlocal slept
        del delay
        slept = True

    monkeypatch.setattr("app.services.agent_core.core.retry.asyncio.sleep", fake_sleep)

    with pytest.raises(asyncio.CancelledError):
        await run_with_retry(operation)

    assert attempts == 1
    assert slept is False
