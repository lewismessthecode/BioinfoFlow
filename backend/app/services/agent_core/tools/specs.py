from __future__ import annotations

from collections.abc import Awaitable, Callable
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
    # Opt-in concurrency contract. A read risk level alone is insufficient:
    # tools must explicitly attest that independent invocations are safe to run
    # concurrently and do not rely on another call's side effects.
    parallel_safe: bool = False
    # Orthogonal pause signal: when set, the tool always pauses for the user
    # regardless of permission_mode (even ``bypass``). Values: ``"user_input"``
    # (ask_user clarification) and ``"plan_approval"`` (exit_plan_mode). This is
    # distinct from risk-gated approvals, which are driven by the permission
    # policy.
    interaction: str | None = None

    def __post_init__(self) -> None:
        if not self.parallel_safe:
            return
        if self.risk_level != "read":
            raise ValueError("parallel-safe tools must be read-only")
        if self.write_scope:
            raise ValueError("parallel-safe tools cannot declare a write scope")
        if self.interaction is not None:
            raise ValueError("parallel-safe tools cannot be interaction tools")


@dataclass(frozen=True)
class AgentToolContext:
    db: AsyncSession
    workspace_id: str
    user_id: str
    session_id: str
    turn_id: str
    permission_context_snapshot: dict[str, Any] | None = None
    ownership_guard: Callable[[], Awaitable[None]] | None = None
    expected_owner_token: str | None = None

    async def ensure_turn_ownership(self) -> None:
        if self.ownership_guard is not None:
            await self.ownership_guard()


class AgentTool(Protocol):
    spec: AgentToolSpec

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        """Run the tool through typed platform/domain service boundaries."""
