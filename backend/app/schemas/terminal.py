from __future__ import annotations

from pydantic import BaseModel


class TerminalSessionCreate(BaseModel):
    project_id: str


class TerminalSessionRead(BaseModel):
    id: str
    project_id: str
    shell: str
    cwd: str
    status: str


class TerminalSessionCloseResponse(BaseModel):
    id: str
    closed: bool
