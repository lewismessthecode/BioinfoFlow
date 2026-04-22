"""Centralized error-handling decorator for API route handlers.

Catches common Python and project-specific exceptions and maps them to the
standard ``error_response`` envelope so that individual routes no longer need
repetitive try/except blocks.

Usage::

    from app.api.error_handler import handle_api_errors

    @router.get("/{item_id}")
    @handle_api_errors
    async def get_item(item_id: str, request: Request, ...):
        ...

    # Override the default code for FileNotFoundError in a specific route:
    @router.get("/{item_id}")
    @handle_api_errors(FileNotFoundError=("FILE_NOT_FOUND", 404))
    async def get_item(item_id: str, request: Request, ...):
        ...
"""

from __future__ import annotations

import functools
import inspect
import logging
from typing import Any, Callable

from fastapi import Request

from app.utils.exceptions import AppError
from app.utils.responses import error_response

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default Python exception -> (error_code, status_code) mapping.
# Order matters: more specific types must appear before their parents.
# ---------------------------------------------------------------------------
_BUILTIN_EXCEPTION_MAP: list[tuple[type[Exception], str, int]] = [
    (FileNotFoundError, "NOT_FOUND", 404),
    (FileExistsError, "CONFLICT", 409),
    (PermissionError, "PERMISSION_DENIED", 403),
    (ValueError, "VALIDATION_ERROR", 422),
]


def _resolve_request(
    args: tuple, kwargs: dict[str, Any], sig: inspect.Signature
) -> Request | None:
    """Extract the ``request`` parameter from the endpoint's call arguments."""
    if "request" in kwargs:
        return kwargs["request"]
    for idx, (name, _param) in enumerate(sig.parameters.items()):
        if name == "request" and idx < len(args):
            return args[idx]
    return None


def _build_wrapper(
    fn: Callable,
    overrides: dict[type[Exception], tuple[str, int]],
) -> Callable:
    sig = inspect.signature(fn)

    # Merge overrides into the default map (overrides take precedence)
    override_types = set(overrides)
    exc_map: list[tuple[type[Exception], str, int]] = [
        (cls, *overrides[cls]) if cls in override_types else (cls, code, status)
        for cls, code, status in _BUILTIN_EXCEPTION_MAP
    ]

    # Derive the except clause from the map — avoids hardcoding types twice
    _catchable = tuple(cls for cls, _, _ in exc_map)

    @functools.wraps(fn)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        request = _resolve_request(args, kwargs, sig)
        try:
            return await fn(*args, **kwargs)
        except AppError as exc:
            return error_response(
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
                details=exc.details,
                request=request,
            )
        except _catchable as exc:
            for cls, code, status in exc_map:
                if isinstance(exc, cls):
                    return error_response(
                        code=code,
                        message=str(exc),
                        status_code=status,
                        request=request,
                    )
            # Should not reach here, but satisfy the type checker
            raise  # pragma: no cover
        except Exception:
            logger.exception("Unhandled error in %s", fn.__qualname__)
            return error_response(
                code="INTERNAL_ERROR",
                message="An internal error occurred",
                status_code=500,
                request=request,
            )

    return wrapper


def handle_api_errors(
    fn: Callable | None = None,
    /,
    **overrides: tuple[str, int],
) -> Callable:
    """Decorator that wraps an async endpoint with centralized error handling.

    Can be used bare or with keyword overrides to change the default mapping
    for specific exception types::

        @handle_api_errors                         # bare — uses defaults
        @handle_api_errors(ValueError=("CONFLICT", 409))  # override ValueError

    Exceptions are resolved in this priority order:

    1. ``AppError`` subclasses (carry their own code / status / details).
    2. Built-in Python exceptions listed in the mapping table.
    3. Any other exception -> generic 500 without leaking internals.
    """

    # Resolve the name-based overrides to actual exception types.
    _NAME_TO_TYPE: dict[str, type[Exception]] = {
        "FileNotFoundError": FileNotFoundError,
        "FileExistsError": FileExistsError,
        "PermissionError": PermissionError,
        "ValueError": ValueError,
    }
    typed_overrides: dict[type[Exception], tuple[str, int]] = {}
    for name, mapping in overrides.items():
        exc_type = _NAME_TO_TYPE.get(name)
        if exc_type is None:
            raise TypeError(f"Unsupported override exception: {name}")
        typed_overrides[exc_type] = mapping

    if fn is not None:
        # Bare decorator: @handle_api_errors
        return _build_wrapper(fn, typed_overrides)

    # Parameterized decorator: @handle_api_errors(...)
    def decorator(f: Callable) -> Callable:
        return _build_wrapper(f, typed_overrides)

    return decorator
