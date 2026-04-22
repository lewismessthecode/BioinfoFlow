from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Generic, TypeVar

from pydantic import BaseModel, Field


class Pagination(BaseModel):
    limit: int
    has_more: bool
    next_cursor: str | None = None
    total_count: int | None = None


class Meta(BaseModel):
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    request_id: str
    pagination: Pagination | None = None
    status: dict[str, Any] | None = None


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Any | None = None


DataT = TypeVar("DataT")


class Envelope(BaseModel, Generic[DataT]):
    success: bool
    data: DataT | None = None
    error: ErrorDetail | None = None
    meta: Meta
