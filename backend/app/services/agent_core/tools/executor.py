from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentActionStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentArtifactRepository,
)
from app.services.agent_core.actions import AgentActionService
from app.services.agent_core.core.lease import (
    LEASE_LOSS_CANCELLATION,
    is_lease_loss_cancellation,
)
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.metrics import agent_metrics
from app.services.agent_core.permissions.context import (
    PermissionContext,
    PermissionContextResolver,
)
from app.services.agent_core.permissions.risk import RiskAssessment
from app.services.agent_core.permissions.command_risk import (
    CommandRiskAssessment,
    command_target_profile_from_context,
)
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
        completed = sum(
            1
            for todo in todos
            if isinstance(todo, dict) and todo.get("status") == "completed"
        )
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
        inner = (
            result.get(artifact_type)
            if isinstance(result.get(artifact_type), dict)
            else result
        )
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
        artifact_type
        in {"command", "remote_command", "remote_file", "remote_directory"}
        or policy.get("stdout")
        or policy.get("stderr")
    ) and any(key in command_result for key in ("stdout", "stderr", "exit_code")):
        return None
    return None


def _resolve_requested_risk(
    tool: AgentTool,
    normalized_input: dict[str, Any],
    permission_context: PermissionContext,
):
    """Let a tool dynamically raise its requested risk from its input.

    Most tools declare a static ``risk_level``. The ``bash`` tool overrides
    ``assess_risk`` to classify the actual command string, so a destructive
    command escalates to ask/deny while a safe one auto-runs. The static spec
    level is the floor when no dynamic assessment applies.
    """
    assess = getattr(tool, "assess_risk", None)
    if assess is not None:
        dynamic = assess(
            normalized_input or {},
            target=command_target_profile_from_context(
                permission_context,
                action_input=normalized_input,
            ),
        )
        if dynamic is not None:
            return dynamic
    return tool.spec.risk_level


def _produce_risk_assessment(
    *,
    tool: AgentTool,
    action_input: dict[str, Any],
    action_service: AgentActionService,
    permission_context: PermissionContext,
) -> RiskAssessment:
    requested = _resolve_requested_risk(tool, action_input, permission_context)
    if isinstance(requested, RiskAssessment):
        return requested
    return action_service.risk_engine.assess(
        kind="tool",
        name=tool.spec.name,
        requested_level=requested,
        input=action_input,
    )


def _snapshot_with_command_risk(
    snapshot: dict[str, Any], risk: RiskAssessment
) -> dict[str, Any]:
    if not isinstance(risk, CommandRiskAssessment):
        return snapshot
    return {**snapshot, "command_risk": risk.audit_snapshot()}


def _has_explicit_user_approval(permission_decision: dict[str, Any]) -> bool:
    if permission_decision.get("decision") not in {"approve", "modify", "answer"}:
        return False
    # Historical user decisions predate the source field. Policy-produced
    # decisions use ``allow``/``ask``/``deny``, so a legacy approve remains a
    # safe, unambiguous compatibility case.
    return permission_decision.get("source") in {
        None,
        "user",
        "user_pending_strategy",
    }


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
        tool_batch_id: str | None = None,
        tool_call_ordinal: int | None = None,
        defer_execution: bool = False,
        commit_action: bool = True,
        role: str = "orchestrator",
        execution_target: dict | str | None = None,
    ) -> ToolExecutionResult:
        tool = self.registry.get(tool_name)
        permission_context = await PermissionContextResolver(self.session).resolve(
            session_id=context.session_id,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        permission_snapshot = permission_context.snapshot()
        toolset_policy = permission_snapshot["toolset_policy"]
        permission_mode = permission_context.permission_mode
        automation_mode = permission_context.automation_mode
        role = permission_context.role
        execution_target = permission_snapshot["execution_target"]
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
                tool_batch_id=tool_batch_id,
                tool_call_ordinal=tool_call_ordinal,
                permission_context=permission_context,
                exc=exc,
                commit=commit_action,
            )
        requested_risk = _resolve_requested_risk(
            tool,
            normalized_input,
            permission_context,
        )
        permission_snapshot = _snapshot_with_command_risk(
            permission_snapshot,
            requested_risk
            if isinstance(requested_risk, RiskAssessment)
            else self.action_service.risk_engine.assess(
                kind="tool",
                name=tool.spec.name,
                requested_level=requested_risk,
                input=normalized_input,
            ),
        )

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
            tool_batch_id=tool_batch_id,
            tool_call_ordinal=tool_call_ordinal,
            exposure_policy=exposure.policy,
            force_ask=tool.spec.interaction is not None,
            interaction=tool.spec.interaction,
            evaluated_policy_version=permission_context.policy_version,
            permission_context_snapshot=permission_snapshot,
            commit=commit_action,
        )
        if action_requires_resume(action.status):
            update = (
                self.action_repo.update_all
                if commit_action
                else self.action_repo.update_all_pending
            )
            action = await update(action, requires_resume=True)
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

        if defer_execution:
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
        tool_batch_id: str | None,
        tool_call_ordinal: int | None,
        permission_context: PermissionContext,
        exc: BadRequestError,
        commit: bool,
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
            tool_batch_id=tool_batch_id,
            tool_call_ordinal=tool_call_ordinal,
            exposure_policy=exposure_policy,
            force_ask=False,
            interaction=None,
            evaluated_policy_version=permission_context.policy_version,
            permission_context_snapshot=permission_context.snapshot(),
            commit=commit,
        )
        failed = await self.action_repo.fail_requested(
            str(action.id),
            error=error,
            completed_at=datetime.now(timezone.utc),
            expected_turn_owner_token=context.execution_owner_token,
        )
        if failed is None:
            await self.session.rollback()
            if context.execution_owner_token is not None:
                raise asyncio.CancelledError(LEASE_LOSS_CANCELLATION)
            return await self._current_result(str(action.id), fallback=action)
        action = failed
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_FAILED,
            payload={"action_id": str(action.id), "error": error},
            commit=commit,
        )
        agent_metrics.increment("tools.failed")
        return ToolExecutionResult(
            action_id=str(action.id), status=action.status, error=error
        )

    async def resume_action(
        self,
        *,
        action_id: str,
        context: AgentToolContext,
    ) -> ToolExecutionResult:
        action = await self.action_repo.get(action_id)
        if action is None:
            raise PermissionDeniedError("Agent action is not accessible")
        if (
            str(action.session_id) != context.session_id
            or str(action.turn_id) != context.turn_id
        ):
            raise PermissionDeniedError(
                "Agent action is outside the current agent context"
            )
        if action.kind != "tool":
            raise ConflictError("Only tool actions can be resumed")
        if action.status != AgentActionStatus.REQUESTED:
            return ToolExecutionResult(
                action_id=str(action.id),
                status=action.status,
                result=action.result,
                permission_decision=action.permission_decision,
                error=action.error,
            )

        decision = action.permission_decision or {}
        if decision.get("decision") not in {"allow", "approve", "modify", "answer"}:
            raise PermissionDeniedError("Agent action has not been approved")
        tool = self.registry.get(action.name)
        return await self._run_action(action=action, tool=tool, context=context)

    async def cancel_action(
        self,
        *,
        action_id: str,
        reason: str,
        expected_turn_owner_token: str | None = None,
    ) -> ToolExecutionResult:
        action = await self.action_repo.get(action_id)
        if action is None:
            raise ConflictError("Tool action does not exist")
        error = {"type": "InteractionExclusive", "message": reason}
        cancelled = await self.action_repo.cancel_open(
            action_id,
            error=error,
            completed_at=datetime.now(timezone.utc),
            expected_turn_owner_token=expected_turn_owner_token,
        )
        if cancelled is None:
            await self.session.rollback()
            return await self._current_result(action_id, fallback=action)
        action = cancelled
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_CANCELLED,
            payload={
                "action_id": str(action.id),
                "tool": action.name,
                "reason": reason,
            },
        )
        return ToolExecutionResult(
            action_id=str(action.id), status=action.status, error=error
        )

    async def _fail_requested_permission(
        self,
        *,
        action,
        error_message: str,
        risk: RiskAssessment | None = None,
        permission_decision: dict[str, Any] | None = None,
        evaluated_policy_version: int | None = None,
        permission_context_snapshot: dict[str, Any] | None = None,
        expected_turn_owner_token: str | None = None,
    ) -> ToolExecutionResult:
        error = {"type": "PermissionDeniedError", "message": error_message}
        failed = await self.action_repo.fail_requested(
            str(action.id),
            error=error,
            completed_at=datetime.now(timezone.utc),
            risk_level=risk.level if risk is not None else None,
            risk_reasons=risk.reasons if risk is not None else None,
            affected_resources=risk.affected_resources if risk is not None else None,
            permission_decision=permission_decision,
            evaluated_policy_version=evaluated_policy_version,
            permission_context_snapshot=permission_context_snapshot,
            expected_turn_owner_token=expected_turn_owner_token,
        )
        if failed is None:
            await self.session.rollback()
            if expected_turn_owner_token is not None:
                raise asyncio.CancelledError(LEASE_LOSS_CANCELLATION)
            return await self._current_result(str(action.id), fallback=action)
        await self.ledger.append(
            session_id=str(failed.session_id),
            turn_id=str(failed.turn_id),
            type=AgentEventType.ACTION_FAILED,
            payload={"action_id": str(failed.id), "error": error},
            commit=False,
        )
        await self.session.commit()
        agent_metrics.increment("tools.failed")
        return ToolExecutionResult(
            action_id=str(failed.id),
            status=failed.status,
            error=error,
        )

    async def _current_result(self, action_id: str, *, fallback) -> ToolExecutionResult:
        current = await self.action_repo.get_fresh(action_id)
        return ToolExecutionResult(
            action_id=str(current.id) if current is not None else action_id,
            status=current.status if current is not None else fallback.status,
            result=current.result if current is not None else fallback.result,
            permission_decision=(
                current.permission_decision
                if current is not None
                else fallback.permission_decision
            ),
            error=current.error if current is not None else fallback.error,
            requires_resume=(
                bool(current.requires_resume)
                if current is not None
                else bool(fallback.requires_resume)
            ),
        )

    async def _run_action(
        self,
        *,
        action,
        tool: AgentTool,
        context: AgentToolContext,
        policy_recheck_attempt: int = 0,
    ) -> ToolExecutionResult:
        action_id = str(action.id)
        action = await self.action_repo.get_fresh(action_id)
        if action is None:
            raise PermissionDeniedError("Agent action is not accessible")
        if action.status != AgentActionStatus.REQUESTED:
            await self.session.rollback()
            return await self._current_result(action_id, fallback=action)

        permission_context = await PermissionContextResolver(self.session).resolve(
            session_id=context.session_id,
            workspace_id=context.workspace_id,
            user_id=context.user_id,
        )
        snapshot = permission_context.snapshot()
        exposure = self.exposure.decide(
            tool_name=tool.spec.name,
            policy=snapshot["toolset_policy"],
            role=permission_context.role,
            execution_target=snapshot["execution_target"],
        )
        if not exposure.allowed:
            return await self._fail_requested_permission(
                action=action,
                error_message="; ".join(exposure.reasons),
                expected_turn_owner_token=context.execution_owner_token,
            )

        current_risk = _produce_risk_assessment(
            tool=tool,
            action_input=action.normalized_input or action.input or {},
            action_service=self.action_service,
            permission_context=permission_context,
        )
        snapshot = _snapshot_with_command_risk(snapshot, current_risk)
        fresh_decision = self.action_service.permission_policy.decide(
            risk=current_risk,
            permission_mode=permission_context.permission_mode,
            automation_mode=permission_context.automation_mode,
        )
        previous_decision = action.permission_decision or {}
        explicitly_approved = _has_explicit_user_approval(previous_decision)
        hard_denied = (
            fresh_decision.decision == "deny"
            or current_risk.level == "critical"
            or getattr(current_risk, "hard_blocked", False)
            or previous_decision.get("hard_blocked") is True
            or previous_decision.get("protected_resource_recheck") == "deny"
        )
        if hard_denied:
            denied_decision = {
                **fresh_decision.as_dict(),
                "source": "policy_recheck",
                "evaluated_policy_version": permission_context.policy_version,
                "requires_explicit_approval": current_risk.requires_explicit_approval,
                "hard_blocked": True,
            }
            return await self._fail_requested_permission(
                action=action,
                error_message="Action is hard-blocked by the current safety floor.",
                risk=current_risk,
                permission_decision=denied_decision,
                evaluated_policy_version=permission_context.policy_version,
                permission_context_snapshot=snapshot,
                expected_turn_owner_token=context.execution_owner_token,
            )

        requires_approval = (
            fresh_decision.decision == "ask" or current_risk.requires_explicit_approval
        )
        if requires_approval and not explicitly_approved:
            permission_decision = {
                **fresh_decision.as_dict(),
                "source": "policy_recheck",
                "evaluated_policy_version": permission_context.policy_version,
                "requires_explicit_approval": (current_risk.requires_explicit_approval),
            }
            waiting = await self.action_repo.defer_requested_for_approval(
                action_id,
                risk_level=current_risk.level,
                risk_reasons=current_risk.reasons,
                affected_resources=current_risk.affected_resources,
                permission_decision=permission_decision,
                evaluated_policy_version=permission_context.policy_version,
                permission_context_snapshot=snapshot,
                expected_turn_owner_token=context.execution_owner_token,
            )
            if waiting is None:
                await self.session.rollback()
                return await self._current_result(action_id, fallback=action)
            await self.ledger.append(
                session_id=str(waiting.session_id),
                turn_id=str(waiting.turn_id),
                type=AgentEventType.ACTION_WAITING_DECISION,
                payload={
                    "action_id": str(waiting.id),
                    "name": waiting.name,
                    "kind": waiting.kind,
                    "risk_level": current_risk.level,
                    "tool_call_id": waiting.tool_call_id,
                    "input_preview": waiting.input_preview,
                    "evaluated_policy_version": permission_context.policy_version,
                    "recheck": True,
                },
                commit=False,
            )
            await self.session.commit()
            return ToolExecutionResult(
                action_id=str(waiting.id),
                status=waiting.status,
                permission_decision=permission_decision,
                requires_resume=True,
            )

        permission_decision = (
            {
                **previous_decision,
                "rechecked_policy_version": permission_context.policy_version,
                "recheck_decision": fresh_decision.as_dict(),
                "requires_explicit_approval": (current_risk.requires_explicit_approval),
            }
            if explicitly_approved
            else {
                **fresh_decision.as_dict(),
                "source": "policy_recheck",
                "evaluated_policy_version": permission_context.policy_version,
                "requires_explicit_approval": (current_risk.requires_explicit_approval),
            }
        )
        requested_action = action
        action = await self.action_repo.claim_requested(
            action_id,
            started_at=datetime.now(timezone.utc),
            risk_level=current_risk.level,
            risk_reasons=current_risk.reasons,
            affected_resources=current_risk.affected_resources,
            permission_decision=permission_decision,
            evaluated_policy_version=permission_context.policy_version,
            permission_context_snapshot=snapshot,
            expected_policy_version=permission_context.policy_version,
            expected_turn_owner_token=context.execution_owner_token,
        )
        if action is None:
            await self.session.rollback()
            current = await self.action_repo.get_fresh(action_id)
            if (
                current is not None
                and current.status == AgentActionStatus.REQUESTED
                and policy_recheck_attempt < 3
            ):
                return await self._run_action(
                    action=current,
                    tool=tool,
                    context=context,
                    policy_recheck_attempt=policy_recheck_attempt + 1,
                )
            if current is not None and current.status == AgentActionStatus.REQUESTED:
                return await self._fail_requested_permission(
                    action=current,
                    error_message=(
                        "Permission policy changed repeatedly before the action "
                        "could be claimed."
                    ),
                    expected_turn_owner_token=context.execution_owner_token,
                )
            return await self._current_result(action_id, fallback=requested_action)
        try:
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_STARTED,
                payload={
                    "action_id": str(action.id),
                    "tool": tool.spec.name,
                    "name": action.name,
                    "tool_call_id": str(action.tool_call_id)
                    if action.tool_call_id
                    else None,
                    "input_preview": action.input_preview,
                },
                commit=False,
            )
            await self.session.commit()
        except Exception:
            await self.session.rollback()
            raise
        agent_metrics.increment("tools.started")
        execution_context = replace(
            context,
            permission_context_snapshot=snapshot,
        )
        try:
            raw_result = await asyncio.wait_for(
                tool.run(action.normalized_input or action.input, execution_context),
                timeout=tool.spec.timeout_seconds,
            )
            validated_result = validate_tool_output(raw_result, tool.spec.output_schema)
            result, summary = normalize_tool_result(validated_result)
        except asyncio.TimeoutError:
            error = {
                "type": "TimeoutError",
                "message": f"Tool timed out after {tool.spec.timeout_seconds}s",
            }
            failed = await self.action_repo.transition_running(
                str(action.id),
                status=AgentActionStatus.FAILED,
                error=error,
                completed_at=datetime.now(timezone.utc),
                expected_turn_owner_token=execution_context.execution_owner_token,
            )
            if failed is None:
                await self.session.rollback()
                return await self._current_result(action_id, fallback=action)
            action = failed
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(action.id), "error": error},
                commit=False,
            )
            await self.session.commit()
            agent_metrics.increment("tools.failed")
            return ToolExecutionResult(
                action_id=str(action.id), status=action.status, error=error
            )
        except asyncio.CancelledError as exc:
            if is_lease_loss_cancellation(exc):
                await self.session.rollback()
                raise
            cancelled = await self.action_repo.transition_running(
                str(action.id),
                status=AgentActionStatus.CANCELLED,
                error={
                    "type": "CancelledError",
                    "message": "Tool execution was cancelled.",
                },
                completed_at=datetime.now(timezone.utc),
                expected_turn_owner_token=execution_context.execution_owner_token,
            )
            if cancelled is None:
                await self.session.rollback()
                raise
            action = cancelled
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={"action_id": str(action.id), "tool": tool.spec.name},
                commit=False,
            )
            await self.session.commit()
            agent_metrics.increment("tools.cancelled")
            raise
        except Exception as exc:
            error = {"type": exc.__class__.__name__, "message": str(exc)}
            failed = await self.action_repo.transition_running(
                str(action.id),
                status=AgentActionStatus.FAILED,
                error=error,
                completed_at=datetime.now(timezone.utc),
                expected_turn_owner_token=execution_context.execution_owner_token,
            )
            if failed is None:
                await self.session.rollback()
                return await self._current_result(action_id, fallback=action)
            action = failed
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_FAILED,
                payload={"action_id": str(action.id), "error": error},
                commit=False,
            )
            await self.session.commit()
            agent_metrics.increment("tools.failed")
            return ToolExecutionResult(
                action_id=str(action.id), status=action.status, error=error
            )

        completed = await self.action_repo.transition_running(
            str(action.id),
            status=AgentActionStatus.COMPLETED,
            result=result,
            output_summary=summary,
            completed_at=datetime.now(timezone.utc),
            expected_turn_owner_token=execution_context.execution_owner_token,
        )
        if completed is None:
            await self.session.rollback()
            return await self._current_result(action_id, fallback=action)
        action = completed
        artifact_ids = await self._register_artifacts(
            action=action, tool=tool, result=result
        )
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_COMPLETED,
            payload={
                "action_id": str(action.id),
                "name": action.name,
                "tool_call_id": str(action.tool_call_id)
                if action.tool_call_id
                else None,
                "input_preview": action.input_preview,
                "result": result,
                "artifact_ids": artifact_ids,
            },
            commit=False,
        )
        await self.session.commit()
        agent_metrics.increment("tools.completed")
        return ToolExecutionResult(
            action_id=str(action.id),
            status=action.status,
            result=result,
            permission_decision=action.permission_decision,
        )

    async def _register_artifacts(
        self, *, action, tool: AgentTool, result: dict[str, Any]
    ) -> list[str]:
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
