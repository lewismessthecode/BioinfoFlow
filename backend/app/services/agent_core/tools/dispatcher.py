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
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.specs import AgentTool, AgentToolContext
from app.utils.exceptions import ConflictError, PermissionDeniedError


@dataclass(frozen=True)
class ToolDispatchResult:
    action_id: str
    status: str
    result: dict[str, Any] | None = None
    permission_decision: dict[str, Any] | None = None
    error: dict[str, Any] | None = None


class AgentToolDispatcher:
    def __init__(self, session: AsyncSession, registry: AgentToolRegistry):
        self.session = session
        self.registry = registry
        self.action_service = AgentActionService(session)
        self.action_repo = AgentActionRepository(session)
        self.artifact_repo = AgentArtifactRepository(session)
        self.ledger = AgentEventLedger(session)

    async def dispatch(
        self,
        *,
        tool_name: str,
        input: dict[str, Any],
        context: AgentToolContext,
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
    ) -> ToolDispatchResult:
        tool = self.registry.get(tool_name)
        action = await self.action_service.request_action(
            turn_id=context.turn_id,
            kind="tool",
            name=tool.spec.name,
            input=input,
            requested_risk=tool.spec.risk_level,
            permission_mode=permission_mode,
            automation_mode=automation_mode,
            read_scope=tool.spec.read_scope,
            write_scope=tool.spec.write_scope,
            rollback_hint=tool.spec.rollback_hint,
            artifact_policy=tool.spec.artifact_policy,
        )
        if action.status != AgentActionStatus.REQUESTED:
            return ToolDispatchResult(
                action_id=str(action.id),
                status=action.status,
                permission_decision=action.permission_decision,
            )

        return await self._run_action(action=action, tool=tool, context=context)

    async def resume_action(
        self,
        *,
        action_id: str,
        context: AgentToolContext,
    ) -> ToolDispatchResult:
        action = await self.action_repo.get(action_id)
        if action is None:
            raise PermissionDeniedError("Agent action is not accessible")
        if str(action.session_id) != context.session_id or str(action.turn_id) != context.turn_id:
            raise PermissionDeniedError("Agent action is outside the current agent context")
        if action.kind != "tool":
            raise ConflictError("Only tool actions can be resumed by the tool dispatcher")
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
    ) -> ToolDispatchResult:
        started_at = datetime.now(timezone.utc)
        action = await self.action_repo.update_all(
            action,
            status=AgentActionStatus.RUNNING,
            started_at=started_at,
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_STARTED,
            payload={"action_id": str(action.id), "tool": tool.spec.name},
        )
        try:
            result = await tool.run(action.input, context)
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
            return ToolDispatchResult(
                action_id=str(action.id),
                status=action.status,
                permission_decision=action.permission_decision,
                error=error,
            )

        artifact_ids = await self._register_artifacts(
            action=action,
            tool=tool,
            result=result,
        )
        action = await self.action_repo.update_all(
            action,
            status=AgentActionStatus.COMPLETED,
            result=result,
            completed_at=datetime.now(timezone.utc),
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_COMPLETED,
            payload={"action_id": str(action.id), "result": result, "artifact_ids": artifact_ids},
        )
        return ToolDispatchResult(
            action_id=str(action.id),
            status=action.status,
            result=result,
            permission_decision=action.permission_decision,
        )

    async def _register_artifacts(
        self,
        *,
        action,
        tool: AgentTool,
        result: dict[str, Any],
    ) -> list[str]:
        policy = action.artifact_policy or tool.spec.artifact_policy or {}
        if not (policy.get("stdout") or policy.get("stderr")):
            return []
        if not any(key in result for key in ("stdout", "stderr", "exit_code")):
            return []

        exit_code = result.get("exit_code")
        artifact = await self.artifact_repo.create(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            action_id=str(action.id),
            type="log_summary",
            title=f"{tool.spec.name} output",
            summary=(
                f"Command exited with code {exit_code}."
                if exit_code is not None
                else "Tool output captured."
            ),
            payload={
                "tool": tool.spec.name,
                "command": action.input.get("command"),
                "cwd": result.get("cwd") or action.input.get("cwd"),
                "exit_code": exit_code,
                "stdout": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            },
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
