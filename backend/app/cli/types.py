"""Pure dataclass / exception types for the CLI.

Kept in a separate module so callers (errors, render, api_helpers, command
helpers) can import them without dragging in `httpx` and the rest of the
network stack — important for `bif --version` / `bif --help` startup time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ApiResponse:
    """Parsed API envelope."""

    success: bool
    data: Any
    error: dict[str, Any] | None
    meta: dict[str, Any] | None
    status_code: int


@dataclass(frozen=True)
class SSEEvent:
    """A single Server-Sent Event."""

    id: str | None
    event: str
    data: str


class ApiError(Exception):
    """Structured error from the API."""

    def __init__(self, code: str, message: str, status_code: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class ConnectionFailed(Exception):
    """Transport-level connection failure."""
