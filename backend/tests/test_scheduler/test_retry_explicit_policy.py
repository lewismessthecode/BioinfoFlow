"""Tests that retry_policy is passed explicitly, not monkey-patched onto ORM models."""

from __future__ import annotations

from app.scheduler.retry import RetryEvaluator


class TestRetryPolicyExplicitParam:
    def test_should_retry_uses_explicit_retry_policy(self):
        """RetryEvaluator.should_retry must accept retry_policy as keyword arg."""
        evaluator = RetryEvaluator()

        # Task with no retry_policy attribute (like a real ORM model)
        task = type(
            "Task",
            (),
            {"attempt": 1, "max_attempts": 3},
        )()
        assert not hasattr(task, "retry_policy")

        # Pass retry_policy explicitly
        policy = {
            "max_retries": 2,
            "delay_seconds": 10,
            "retry_on": ["oom", "137"],
        }
        assert evaluator.should_retry(task, "exit 137", retry_policy=policy) is True
        assert (
            evaluator.should_retry(task, "validation error", retry_policy=policy)
            is False
        )

    def test_next_delay_uses_explicit_retry_policy(self):
        """RetryEvaluator.next_delay must accept retry_policy as keyword arg."""
        evaluator = RetryEvaluator()

        task = type(
            "Task",
            (),
            {"attempt": 2, "max_attempts": 4},
        )()
        assert not hasattr(task, "retry_policy")

        policy = {
            "max_retries": 3,
            "delay_seconds": 10,
            "backoff_multiplier": 2.0,
            "max_delay_seconds": 100,
        }
        delay = evaluator.next_delay(task, retry_policy=policy)
        # attempt=2, so delay = 10 * 2^(2-1) = 20
        assert delay == 20.0

    def test_falls_back_to_task_attribute_when_no_explicit_policy(self):
        """Backward compat: if no explicit policy, read from task attribute."""
        evaluator = RetryEvaluator()

        task = type(
            "Task",
            (),
            {
                "attempt": 1,
                "max_attempts": 3,
                "retry_policy": {
                    "max_retries": 2,
                    "retry_on": ["oom"],
                },
            },
        )()

        assert evaluator.should_retry(task, "oom killed") is True
        assert evaluator.should_retry(task, "validation error") is False

    def test_explicit_policy_overrides_task_attribute(self):
        """Explicit retry_policy kwarg takes precedence over task attribute."""
        evaluator = RetryEvaluator()

        task = type(
            "Task",
            (),
            {
                "attempt": 1,
                "max_attempts": 3,
                "retry_policy": {
                    "max_retries": 2,
                    "retry_on": ["oom"],
                },
            },
        )()

        # Task attribute says retry on "oom" only, but explicit says retry on "timeout"
        explicit = {"max_retries": 2, "retry_on": ["timeout"]}
        assert (
            evaluator.should_retry(task, "oom killed", retry_policy=explicit) is False
        )
        assert (
            evaluator.should_retry(task, "connection timeout", retry_policy=explicit)
            is True
        )
