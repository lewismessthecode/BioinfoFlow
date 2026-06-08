from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentToolContext


@dataclass(frozen=True)
class ToolDispatchResult:
    action_id: str
    status: str
    result: dict[str, Any] | None = None
    permission_decision: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class AgentToolDispatcher:
    """Compatibility facade for callers that predate the harness executor."""

    def __init__(self, session: AsyncSession, registry: AgentToolRegistry):
        self.executor = AgentToolExecutor(session, registry)

    async def dispatch(
        self,
        *,
        tool_name: str,
        input: dict[str, Any],
        context: AgentToolContext,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
    ) -> ToolDispatchResult:
        result = await self.executor.execute(
            tool_name=tool_name,
            input=input,
            context=context,
            toolset_policy={"name": "execution"},
            permission_mode=permission_mode,
            automation_mode=automation_mode,
        )
        return ToolDispatchResult(
            action_id=result.action_id,
            status=result.status,
            result=result.result,
            permission_decision=result.permission_decision,
            error=result.error,
        )

    async def resume_action(
        self,
        *,
        action_id: str,
        context: AgentToolContext,
    ) -> ToolDispatchResult:
        result = await self.executor.resume_action(action_id=action_id, context=context)
        return ToolDispatchResult(
            action_id=result.action_id,
            status=result.status,
            result=result.result,
            permission_decision=result.permission_decision,
            error=result.error,
        )
