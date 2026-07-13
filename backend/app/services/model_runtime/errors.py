from __future__ import annotations

from dataclasses import FrozenInstanceError
from typing import Literal, TypeAlias


ModelErrorCategory: TypeAlias = Literal[
    "authentication",
    "authorization",
    "rate_limit",
    "timeout",
    "connection",
    "service_unavailable",
    "invalid_request",
    "not_found",
    "conflict",
    "unsupported",
    "provider",
    "unknown",
]


class ModelError(Exception):
    """A provider-neutral model failure with an explicitly safe public message."""

    __slots__ = (
        "category",
        "message",
        "http_status",
        "provider_code",
        "retryable",
        "replay_safe",
        "retry_after_seconds",
        "request_id",
        "_cause",
        "_initialized",
    )

    def __init__(
        self,
        *,
        category: ModelErrorCategory,
        message: str,
        http_status: int | None = None,
        provider_code: str | None = None,
        retryable: bool = False,
        replay_safe: bool = True,
        retry_after_seconds: float | None = None,
        request_id: str | None = None,
        cause: Exception | None = None,
    ) -> None:
        Exception.__init__(self, message)
        object.__setattr__(self, "category", category)
        object.__setattr__(self, "message", message)
        object.__setattr__(self, "http_status", http_status)
        object.__setattr__(self, "provider_code", provider_code)
        object.__setattr__(self, "retryable", retryable)
        object.__setattr__(self, "replay_safe", replay_safe)
        object.__setattr__(self, "retry_after_seconds", retry_after_seconds)
        object.__setattr__(self, "request_id", request_id)
        object.__setattr__(self, "_cause", cause)
        object.__setattr__(self, "_initialized", True)

    @property
    def cause(self) -> Exception | None:
        return self._cause

    def __setattr__(self, name: str, value: object) -> None:
        if getattr(self, "_initialized", False):
            raise FrozenInstanceError(f"cannot assign to field {name!r}")
        object.__setattr__(self, name, value)

    def __repr__(self) -> str:
        fields = (
            f"category={self.category!r}",
            f"message={self.message!r}",
            f"http_status={self.http_status!r}",
            f"provider_code={self.provider_code!r}",
            f"retryable={self.retryable!r}",
            f"replay_safe={self.replay_safe!r}",
            f"retry_after_seconds={self.retry_after_seconds!r}",
            f"request_id={self.request_id!r}",
        )
        return f"ModelError({', '.join(fields)})"

    def __str__(self) -> str:
        return self.message

    def to_public_dict(self) -> dict[str, str | int | float | bool | None]:
        return {
            "category": self.category,
            "message": self.message,
            "http_status": self.http_status,
            "provider_code": self.provider_code,
            "retryable": self.retryable,
            "replay_safe": self.replay_safe,
            "retry_after_seconds": self.retry_after_seconds,
            "request_id": self.request_id,
        }
