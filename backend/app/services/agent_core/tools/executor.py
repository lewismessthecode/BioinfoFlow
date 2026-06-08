from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository, AgentArtifactRepository
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.tools.approval import action_requires_resume
from app.services.agent_core.tools.middleware import normalize_tool_input
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.result_budget import normalize_tool_result
from app.services.agent_core.tools.specs import AgentTool, AgentToolContext
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.utils.exceptions import ConflictError, PermissionDeniedError


@dataclass(frozen=True)
class ToolExecutionResult:
    action_id: str
    status: str
    result: dict[str, Any] | None = None
    permission_decision: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    requires_resume: bool = False


class AgentToolExecutor:
    def __init__(self, session: AsyncSession, registry: AgentToolRegistry):
        self.session = session
        self.registry = registry
        self.exposure = ToolsetExposure(registry)
        self.action_service = AgentActionService(session)
        self.action_repo = AgentActionRepository(session)
        self.artifact_repo = AgentArtifactRepository(session)
        self.ledger = AgentEventLedger(session)

    async def execute(
        self,
        *,
        tool_name: str,
        input: dict[str, Any],
        context: AgentToolContext,
        toolset_policy: dict | None,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        tool_call_id: str | None = None,
    ) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        exposure = self.exposure.decide(tool_name=tool_name, policy=toolset_policy)
        if not exposure.allowed:
            raise PermissionDeniedError("; ".join(exposure.reasons))
        normalized_input = normalize_tool_input(input, tool.spec.input_schema)

        action = await self.action_service.request_action(
            turn_id=context.turn_id,
            kind="tool",
            name=tool.spec.name,
            input=input,
            normalized_input=normalized_input,
            requested_risk=tool.spec.risk_level,
            permission_mode=permission_mode,
            automation_mode=automation_mode,
            read_scope=tool.spec.read_scope,
            write_scope=tool.spec.write_scope,
            rollback_hint=tool.spec.rollback_hint,
            artifact_policy=tool.spec.artifact_policy,
            tool_call_id=tool_call_id,
            exposure_policy=exposure.policy,
        )
        if action_requires_resume(action.status):
            action = await self.action_repo.update_all(action, requires_resume=True)
            return ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                permission_decision=action.permission_decision,
                requires_resume=True,
            )
        if action.status != AgentActionStatus.REQUESTED:
            return ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                permission_decision=action.permission_decision,
                requires_resume=False,
            )

        return await self._run_action(action=action, tool=tool, context=context)

    async def resume_action(
        self,
        *,
        action_id: str,
        context: AgentToolContext,
    ) -> ToolExecutionResult:
        action = await self.action_repo.get(action_id)
        if action is None:
            raise PermissionDeniedError("Agent action is not accessible")
        if str(action.session_id) != context.session_id or str(action.turn_id) != context.turn_id:
            raise PermissionDeniedError("Agent action is outside the current agent context")
        if action.kind != "tool":
            raise ConflictError("Only tool actions can be resumed")
        if action.status != AgentActionStatus.REQUESTED:
            raise ConflictError(f"Agent action cannot be resumed from status: {action.status}")

        decision = action.permission_decision or {}
        if decision.get("decision") not in {"allow", "approve", "modify"}:
            raise PermissionDeniedError("Agent action has not been approved")
        tool = self.registry.get(action.name)
        return await self._run_action(action=action, tool=tool, context=context)

    async def _run_action(
        self,
        *,
        action,
        tool: AgentTool,
        context: AgentToolContext,
    ) -> ToolExecutionResult:
        action = await self.action_repo.update_all(
            action,
            status=AgentActionStatus.RUNNING,
            requires_resume=False,
            started_at=datetime.now(timezone.utc),
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_STARTED,
            payload={"action_id": str(action.id), "tool": tool.spec.name},
        )
        try:
            raw_result = await tool.run(action.normalized_input or action.input, context)
            result, summary = normalize_tool_result(raw_result)
        except Exception as exc:
            error = {"type": exc.__class__.__name__, "message": str(exc)}
            action = await self.action_repo.update_all(
                action,
                status=AgentActionStatus.FAILED,
                error=error,
                completed_at=datetime.now(timezone.utc),
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(action.id), "error": error},
            )
            return ToolExecutionResult(action_id=str(action.id), status=action.status, error=error)

        artifact_ids = await self._register_artifacts(action=action, tool=tool, result=result)
        action = await self.action_repo.update_all(
            action,
            status=AgentActionStatus.COMPLETED,
            result=result,
            output_summary=summary,
            completed_at=datetime.now(timezone.utc),
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_COMPLETED,
            payload={"action_id": str(action.id), "result": result, "artifact_ids": artifact_ids},
        )
        return ToolExecutionResult(
            action_id=str(action.id),
            status=action.status,
            result=result,
            permission_decision=action.permission_decision,
        )

    async def _register_artifacts(self, *, action, tool: AgentTool, result: dict[str, Any]) -> list[str]:
        policy = action.artifact_policy or tool.spec.artifact_policy or {}
        if not (policy.get("stdout") or policy.get("stderr")):
            return []
        if not any(key in result for key in ("stdout", "stderr", "exit_code")):
            return []
        artifact = await self.artifact_repo.create(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            action_id=str(action.id),
            type="log_summary",
            title=f"{tool.spec.name} output",
            summary="Tool output captured.",
            payload=result,
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ARTIFACT_CREATED,
            payload={
                "artifact_id": str(artifact.id),
                "action_id": str(action.id),
                "type": artifact.type,
                "title": artifact.title,
            },
        )
        return [str(artifact.id)]
