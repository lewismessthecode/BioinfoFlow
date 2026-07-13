from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

import app.database as app_database
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentSessionRepository,
)
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import execution_target_from_session
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


class _DurableActionCancelled(Exception):
    pass


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

    # Command / log output stays in action results and timeline activity, not
    # review artifacts. Artifacts are reserved for user-facing deliverables.
    command_result = result
    if isinstance(result.get("result"), dict):
        command_result = result["result"]
    if (
        artifact_type in {"command", "remote_command", "remote_file", "remote_directory"}
        or policy.get("stdout")
        or policy.get("stderr")
    ) and any(key in command_result for key in ("stdout", "stderr", "exit_code")):
        return None
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


def _tool_role(session) -> str:
    if session is not None and str(getattr(session, "role_profile", "")) == "worker":
        return "worker"
    return "orchestrator"


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
        execution_target: dict | str | None = None,
    ) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        session = await self._session_for_context(context)
        if session is not None:
            execution_target = execution_target_from_session(session)
        exposure = self.exposure.decide(
            tool_name=tool_name,
            policy=toolset_policy,
            role=role,
            execution_target=execution_target,
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
            exposure_policy={
                **exposure.policy,
                "execution_target": execution_target,
            },
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
        session = await self._session_for_context(context)
        current_execution_target = (
            execution_target_from_session(session) if session is not None else None
        )
        approved_execution_target = (action.exposure_policy or {}).get(
            "execution_target"
        )
        if (
            approved_execution_target is None
            or current_execution_target != approved_execution_target
        ):
            return await self._record_permission_failure(
                action=action,
                error_type="ExecutionTargetMismatch",
                error_message=(
                    "Approved action execution target no longer matches the current "
                    f"session target: approved={approved_execution_target!r}, "
                    f"current={current_execution_target!r}"
                ),
            )
        exposure = self.exposure.decide(
            tool_name=tool.spec.name,
            policy=(
                getattr(session, "toolset_policy", None)
                if session is not None
                else action.exposure_policy
            ),
            role=_tool_role(session),
            execution_target=(
                execution_target_from_session(session) if session is not None else None
            ),
        )
        if not exposure.allowed:
            return await self._record_permission_failure(
                action=action,
                error_message="; ".join(exposure.reasons),
            )
        return await self._run_action(action=action, tool=tool, context=context)

    async def _session_for_context(self, context: AgentToolContext):
        session_id = getattr(context, "session_id", None)
        if not session_id:
            return None
        try:
            UUID(str(session_id))
        except (TypeError, ValueError):
            return None
        session = await AgentSessionRepository(self.session).get(str(session_id))
        if session is None:
            return None
        if (
            str(session.workspace_id) != str(context.workspace_id)
            or str(session.user_id) != str(context.user_id)
        ):
            return None
        return session

    async def _record_permission_failure(
        self,
        *,
        action,
        error_message: str,
        error_type: str = "PermissionDeniedError",
    ) -> ToolExecutionResult:
        error = {"type": error_type, "message": error_message}
        updated = await self.action_repo.transition_if_status(
            str(action.id),
            expected_statuses=[AgentActionStatus.REQUESTED],
            status=AgentActionStatus.FAILED,
            error=error,
            completed_at=datetime.now(timezone.utc),
            requires_resume=False,
        )
        if updated is None:
            return await self._current_action_result(str(action.id))
        action = updated
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_FAILED,
            payload={"action_id": str(action.id), "error": error},
        )
        agent_metrics.increment("tools.failed")
        return ToolExecutionResult(
            action_id=str(action.id),
            status=action.status,
            error=error,
        )

    async def _current_action_result(self, action_id: str) -> ToolExecutionResult:
        current = await self.action_repo.get(action_id)
        if current is None:
            raise ConflictError("Agent action disappeared during execution")
        await self.session.refresh(current)
        return ToolExecutionResult(
            action_id=str(current.id),
            status=current.status,
            result=current.result,
            permission_decision=current.permission_decision,
            error=current.error,
            requires_resume=bool(current.requires_resume),
        )

    async def _run_action(
        self,
        *,
        action,
        tool: AgentTool,
        context: AgentToolContext,
    ) -> ToolExecutionResult:
        claimed = await self.action_repo.claim_requested(
            str(action.id),
            started_at=datetime.now(timezone.utc),
        )
        if claimed is None:
            current = await self.action_repo.get(str(action.id))
            if current is None:
                raise ConflictError("Agent action disappeared before execution")
            await self.session.refresh(current)
            return ToolExecutionResult(
                action_id=str(current.id),
                status=current.status,
                result=current.result,
                permission_decision=current.permission_decision,
                error={
                    "type": "ActionAlreadyClaimed",
                    "message": "Another worker already claimed this approved action.",
                },
                requires_resume=bool(current.requires_resume),
            )
        action = claimed
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_STARTED,
            payload={
                "action_id": str(action.id),
                "tool": tool.spec.name,
                "name": action.name,
                "tool_call_id": str(action.tool_call_id) if action.tool_call_id else None,
                "input_preview": action.input_preview,
            },
        )
        agent_metrics.increment("tools.started")
        try:
            raw_result = await self._run_tool_with_cancellation(
                action=action,
                tool=tool,
                context=context,
            )
            validated_result = validate_tool_output(raw_result, tool.spec.output_schema)
            result, summary = normalize_tool_result(validated_result)
        except _DurableActionCancelled:
            return await self._current_action_result(str(action.id))
        except asyncio.TimeoutError:
            error = {
                "type": "TimeoutError",
                "message": f"Tool timed out after {tool.spec.timeout_seconds}s",
            }
            updated = await self.action_repo.transition_if_status(
                str(action.id),
                expected_statuses=[AgentActionStatus.RUNNING],
                status=AgentActionStatus.FAILED,
                error=error,
                completed_at=datetime.now(timezone.utc),
            )
            if updated is None:
                return await self._current_action_result(str(action.id))
            action = updated
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(action.id), "error": error},
            )
            agent_metrics.increment("tools.failed")
            return ToolExecutionResult(action_id=str(action.id), status=action.status, error=error)
        except asyncio.CancelledError:
            updated = await self.action_repo.transition_if_status(
                str(action.id),
                expected_statuses=[AgentActionStatus.RUNNING],
                status=AgentActionStatus.CANCELLED,
                error={"type": "CancelledError", "message": "Tool execution was cancelled."},
                completed_at=datetime.now(timezone.utc),
            )
            if updated is not None:
                action = updated
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
            updated = await self.action_repo.transition_if_status(
                str(action.id),
                expected_statuses=[AgentActionStatus.RUNNING],
                status=AgentActionStatus.FAILED,
                error=error,
                completed_at=datetime.now(timezone.utc),
            )
            if updated is None:
                return await self._current_action_result(str(action.id))
            action = updated
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(action.id), "error": error},
            )
            agent_metrics.increment("tools.failed")
            return ToolExecutionResult(action_id=str(action.id), status=action.status, error=error)

        policy = action.artifact_policy or tool.spec.artifact_policy or {}
        artifact_descriptor = _artifact_descriptor(
            policy=policy,
            tool_name=tool.spec.name,
            result=result,
            action_input=action.normalized_input or action.input or {},
        )
        completed = await self.action_repo.complete_running(
            str(action.id),
            result=result,
            output_summary=summary,
            completed_at=datetime.now(timezone.utc),
            artifact_descriptor=artifact_descriptor,
            artifact_event_type=AgentEventType.ARTIFACT_CREATED,
            action_event_type=AgentEventType.ACTION_COMPLETED,
        )
        if completed is None:
            return await self._current_action_result(str(action.id))
        action, _artifact_ids = completed
        agent_metrics.increment("tools.completed")
        return ToolExecutionResult(
            action_id=str(action.id),
            status=action.status,
            result=result,
            permission_decision=action.permission_decision,
        )

    async def _run_tool_with_cancellation(
        self,
        *,
        action,
        tool: AgentTool,
        context: AgentToolContext,
    ) -> dict[str, Any]:
        tool_task = asyncio.create_task(
            tool.run(action.normalized_input or action.input, context)
        )
        cancellation_task = asyncio.create_task(
            self._wait_for_durable_action_cancellation(str(action.id))
        )
        try:
            done, _pending = await asyncio.wait(
                {tool_task, cancellation_task},
                timeout=tool.spec.timeout_seconds,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if not done:
                tool_task.cancel()
                await asyncio.gather(tool_task, return_exceptions=True)
                raise asyncio.TimeoutError
            if cancellation_task in done and cancellation_task.result():
                tool_task.cancel()
                await asyncio.gather(tool_task, return_exceptions=True)
                raise _DurableActionCancelled
            return await tool_task
        except BaseException:
            tool_task.cancel()
            await asyncio.gather(tool_task, return_exceptions=True)
            raise
        finally:
            cancellation_task.cancel()
            await asyncio.gather(cancellation_task, return_exceptions=True)

    async def _wait_for_durable_action_cancellation(self, action_id: str) -> bool:
        bind = self.session.bind
        session_factory = (
            async_sessionmaker(bind=bind, expire_on_commit=False, class_=AsyncSession)
            if bind is not None
            else app_database.async_session_maker
        )
        async with session_factory() as watcher_db:
            watcher_repo = AgentActionRepository(watcher_db)
            while True:
                await asyncio.sleep(0.05)
                current = await watcher_repo.get(action_id)
                if current is None:
                    return True
                await watcher_db.refresh(current)
                if current.status != AgentActionStatus.RUNNING:
                    return True
