from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.schemas.common import ErrorDetail, Meta, Pagination

_SENSITIVE_TRACE_KEYS = {"traceback", "stack", "stack_trace", "exc_info"}
_REDACTED = "[redacted]"


def _request_id(request: Request | None) -> str:
    if request is None:
        return str(uuid4())
    return request.headers.get("X-Request-ID") or str(uuid4())


def _meta(
    request: Request | None,
    pagination: Pagination | None = None,
    status: dict[str, Any] | None = None,
) -> Meta:
    return Meta(
        timestamp=datetime.now(timezone.utc),
        request_id=_request_id(request),
        pagination=pagination,
        status=status,
    )


def success_response(
    data: Any,
    request: Request | None = None,
    pagination: Pagination | None = None,
    status: dict[str, Any] | None = None,
    status_code: int = 200,
) -> JSONResponse:
    meta = _meta(request, pagination, status)
    if status_code in {204, 205, 304}:
        return Response(status_code=status_code)
    return JSONResponse(
        status_code=status_code,
        # codeql[py/stack-trace-exposure] Successful payloads may include user-requested
        # file/log content. Error envelopes scrub exception details below.
        content={
            "success": True,
            "data": data,
            "meta": meta.model_dump(mode="json"),
        },
    )


def error_response(
    *,
    code: str,
    message: str,
    status_code: int = 400,
    details: Any | None = None,
    request: Request | None = None,
) -> JSONResponse:
    meta = _meta(request)
    error = ErrorDetail(code=code, message=message, details=_scrub_trace_payload(details))
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error.model_dump(mode="json"),
            "meta": meta.model_dump(mode="json"),
        },
    )


def _scrub_trace_payload(value: Any, *, key: str | None = None) -> Any:
    if key and key.lower() in _SENSITIVE_TRACE_KEYS:
        return _REDACTED
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return {
            item_key: _scrub_trace_payload(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_scrub_trace_payload(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_scrub_trace_payload(item) for item in value)
    return value
