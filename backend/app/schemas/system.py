from __future__ import annotations

from pydantic import BaseModel


class DirectoryEntry(BaseModel):
    name: str
    path: str


class DirectoryListResponse(BaseModel):
    path: str
    parent: str | None
    directories: list[DirectoryEntry]
