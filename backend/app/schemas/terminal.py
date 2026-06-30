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
    target_type: str
    target_label: str
    remote_connection_id: str | None = None


class TerminalSessionCloseResponse(BaseModel):
    id: str
    closed: bool
