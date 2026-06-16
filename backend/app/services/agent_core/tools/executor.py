from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import AgentActionRepository, AgentArtifactRepository
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.tools.approval import action_requires_resume
from app.services.agent_core.tools.middleware import (
    normalize_tool_input,
    validate_tool_output,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.result_budget import normalize_tool_result
from app.services.agent_core.tools.specs import AgentTool, AgentToolContext
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.utils.exceptions import BadRequestError, ConflictError, PermissionDeniedError


def _artifact_descriptor(
    *,
    policy: dict[str, Any],
    tool_name: str,
    result: dict[str, Any],
    action_input: dict[str, Any],
) -> dict[str, Any] | None:
    """Build a typed artifact descriptor from a tool result.

    The artifact ``type`` drives the frontend renderer (file diff, command
    terminal, run/workflow/image card, …), so each side-effecting tool tags its
    ``artifact_policy`` with a ``type`` and we shape a payload the panel can use.
    """
    artifact_type = policy.get("type")

    if artifact_type == "todo_list":
        todos = result.get("todos") if isinstance(result.get("todos"), list) else []
        completed = sum(1 for todo in todos if isinstance(todo, dict) and todo.get("status") == "completed")
        return {
            "type": "todo_list",
            "title": "Tasks",
            "summary": f"{completed}/{len(todos)} completed",
            "payload": {"todos": todos},
        }

    if artifact_type == "file":
        path = action_input.get("path")
        content = action_input.get("content")
        if content is None:
            content = action_input.get("new_text")
        bytes_written = result.get("bytes_written")
        replacements = result.get("replacements")
        if bytes_written is not None:
            summary = f"Wrote {bytes_written} bytes"
        elif replacements is not None:
            summary = f"Replaced {replacements} occurrence(s)"
        else:
            summary = "File updated"
        return {
            "type": "file",
            "title": str(path or "file"),
            "summary": summary,
            "payload": {"path": path, "content": content, **result},
        }

    if artifact_type in {"project", "workflow", "run", "image"}:
        inner = result.get(artifact_type) if isinstance(result.get(artifact_type), dict) else result
        title = (
            inner.get("name")
            or inner.get("full_name")
            or inner.get("run_id")
            or inner.get("id")
            or f"{tool_name} {artifact_type}"
        )
        return {
            "type": artifact_type,
            "title": str(title),
            "summary": f"{artifact_type.capitalize()} from {tool_name}.",
            "payload": result,
        }

    # Command / log output (bash and other stdout-producing tools).
    if (artifact_type == "command" or policy.get("stdout") or policy.get("stderr")) and any(
        key in result for key in ("stdout", "stderr", "exit_code")
    ):
        return {
            "type": "command",
            "title": str(result.get("command") or f"{tool_name} output"),
            "summary": f"exit code {result.get('exit_code', '?')}",
            "payload": result,
        }
    return None


def _resolve_requested_risk(tool: AgentTool, normalized_input: dict[str, Any]):
    """Let a tool dynamically raise its requested risk from its input.

    Most tools declare a static ``risk_level``. The ``bash`` tool overrides
    ``assess_risk`` to classify the actual command string, so a destructive
    command escalates to ask/deny while a safe one auto-runs. The static spec
    level is the floor when no dynamic assessment applies.
    """
    assess = getattr(tool, "assess_risk", None)
    if assess is not None:
        dynamic = assess(normalized_input or {})
        if dynamic is not None:
            return dynamic
    return tool.spec.risk_level


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
        role: str = "orchestrator",
    ) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        exposure = self.exposure.decide(
            tool_name=tool_name,
            policy=toolset_policy,
            role=role,
        )
        if not exposure.allowed:
            raise PermissionDeniedError("; ".join(exposure.reasons))
        try:
            normalized_input = normalize_tool_input(input, tool.spec.input_schema)
        except BadRequestError as exc:
            return await self._record_validation_failure(
                tool=tool,
                input=input,
                context=context,
                exposure_policy=exposure.policy,
                automation_mode=automation_mode,
                tool_call_id=tool_call_id,
                exc=exc,
            )
        requested_risk = _resolve_requested_risk(tool, normalized_input)

        action = await self.action_service.request_action(
            turn_id=context.turn_id,
            kind="tool",
            name=tool.spec.name,
            input=input,
            normalized_input=normalized_input,
            requested_risk=requested_risk,
            permission_mode=permission_mode,
            automation_mode=automation_mode,
            read_scope=tool.spec.read_scope,
            write_scope=tool.spec.write_scope,
            rollback_hint=tool.spec.rollback_hint,
            artifact_policy=tool.spec.artifact_policy,
            tool_call_id=tool_call_id,
            exposure_policy=exposure.policy,
            force_ask=tool.spec.interaction is not None,
            interaction=tool.spec.interaction,
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

    async def _record_validation_failure(
        self,
        *,
        tool: AgentTool,
        input: Any,
        context: AgentToolContext,
        exposure_policy: dict | None,
        automation_mode: str,
        tool_call_id: str | None,
        exc: BadRequestError,
    ) -> ToolExecutionResult:
        action_input = input if isinstance(input, dict) else {"_raw_input": input}
        error = {"type": exc.__class__.__name__, "message": str(exc)}
        action = await self.action_service.request_action(
            turn_id=context.turn_id,
            kind="tool",
            name=tool.spec.name,
            input=action_input,
            normalized_input=None,
            requested_risk=tool.spec.risk_level,
            permission_mode="bypass",
            automation_mode=automation_mode,
            read_scope=tool.spec.read_scope,
            write_scope=tool.spec.write_scope,
            rollback_hint=tool.spec.rollback_hint,
            artifact_policy=tool.spec.artifact_policy,
            tool_call_id=tool_call_id,
            exposure_policy=exposure_policy,
            force_ask=False,
            interaction=None,
        )
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
        agent_metrics.increment("tools.failed")
        return ToolExecutionResult(action_id=str(action.id), status=action.status, error=error)

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
        if decision.get("decision") not in {"allow", "approve", "modify", "answer"}:
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
        agent_metrics.increment("tools.started")
        try:
            raw_result = await asyncio.wait_for(
                tool.run(action.normalized_input or action.input, context),
                timeout=tool.spec.timeout_seconds,
            )
            validated_result = validate_tool_output(raw_result, tool.spec.output_schema)
            result, summary = normalize_tool_result(validated_result)
        except asyncio.TimeoutError:
            error = {
                "type": "TimeoutError",
                "message": f"Tool timed out after {tool.spec.timeout_seconds}s",
            }
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
            agent_metrics.increment("tools.failed")
            return ToolExecutionResult(action_id=str(action.id), status=action.status, error=error)
        except asyncio.CancelledError:
            action = await self.action_repo.update_all(
                action,
                status=AgentActionStatus.CANCELLED,
                error={"type": "CancelledError", "message": "Tool execution was cancelled."},
                completed_at=datetime.now(timezone.utc),
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={"action_id": str(action.id), "tool": tool.spec.name},
            )
            agent_metrics.increment("tools.cancelled")
            raise
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
            agent_metrics.increment("tools.failed")
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
        agent_metrics.increment("tools.completed")
        return ToolExecutionResult(
            action_id=str(action.id),
            status=action.status,
            result=result,
            permission_decision=action.permission_decision,
        )

    async def _register_artifacts(self, *, action, tool: AgentTool, result: dict[str, Any]) -> list[str]:
        policy = action.artifact_policy or tool.spec.artifact_policy or {}
        descriptor = _artifact_descriptor(
            policy=policy,
            tool_name=tool.spec.name,
            result=result,
            action_input=action.normalized_input or action.input or {},
        )
        if descriptor is None:
            return []
        artifact = await self.artifact_repo.create(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            action_id=str(action.id),
            type=descriptor["type"],
            title=descriptor["title"],
            summary=descriptor["summary"],
            payload=descriptor["payload"],
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
