from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_core.permissions.risk import RiskLevel


@dataclass(frozen=True)
class AgentToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    risk_level: RiskLevel
    read_scope: list[str] = field(default_factory=list)
    write_scope: list[str] = field(default_factory=list)
    audit: str = ""
    rollback_hint: str | None = None
    timeout_seconds: int = 30
    artifact_policy: dict[str, Any] | None = None


@dataclass(frozen=True)
class AgentToolContext:
    db: AsyncSession
    workspace_id: str
    user_id: str
    session_id: str
    turn_id: str


class AgentTool(Protocol):
    spec: AgentToolSpec

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        """Run the tool through typed platform/domain service boundaries."""
