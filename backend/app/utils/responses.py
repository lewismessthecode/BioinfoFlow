from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import Request
from fastapi.responses import JSONResponse, Response

from app.schemas.common import ErrorDetail, Meta, Pagination


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
        content={"success": True, "data": data, "meta": meta.model_dump(mode="json")},
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
    error = ErrorDetail(code=code, message=message, details=details)
    return JSONResponse(
        status_code=status_code,
        content={
            "success": False,
            "error": error.model_dump(mode="json"),
            "meta": meta.model_dump(mode="json"),
        },
    )
