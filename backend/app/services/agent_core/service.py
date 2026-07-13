from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_core import AgentActionStatus, AgentSessionStatus, AgentTurnStatus
from app.repositories.agent_core_repo import (
    AgentActionRepository,
    AgentArtifactRepository,
    AgentEventRepository,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import (
    execution_target_from_session,
    session_execution_target_from_metadata,
    session_metadata_with_execution_target,
)
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_metadata_with_model_selection,
)
from app.services.agent_core.runner import (
    cancel_turn_run,
    enqueue_turn_resume,
    enqueue_turn_run,
    is_turn_running,
)
from app.services.agent_core.runtime import AgentCoreRuntime
from app.services.agent_core.context import default_system_prompt_snapshot
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.skills import (
    ActiveSkillResolutionError,
    AgentSkillRegistry,
    normalize_skill_names,
    resolve_active_skills,
)
from app.services.agent_core.tools.toolsets import EXECUTION_TOOLSET_POLICY
from app.services.agent_core.tools.approval import action_matches_pending_observation
from app.services.agent_core.transcript import AgentTranscriptStore, text_part
from app.utils.exceptions import BadRequestError, ConflictError, NotFoundError, PermissionDeniedError


class AgentCoreService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.session_repo = AgentSessionRepository(session)
        self.turn_repo = AgentTurnRepository(session)
        self.event_repo = AgentEventRepository(session)
        self.action_repo = AgentActionRepository(session)
        self.artifact_repo = AgentArtifactRepository(session)
        self.project_repo = ProjectRepository(session)
        self.ledger = AgentEventLedger(session)
        self.runtime = AgentCoreRuntime(session)

    async def create_session(
        self,
        *,
        project_id: str,
        workspace_id: str,
        user_id: str,
        title: str | None = None,
        role_profile: str = "bioinformatician",
        permission_mode: str = "guarded_auto",
        automation_mode: str = "assisted",
        default_model_profile_id: str | None = None,
        model_selection: dict | None = None,
        execution_target: dict | None = None,
        metadata: dict | None = None,
        lineage: dict | None = None,
        toolset_policy: dict | None = None,
    ):
        project = None
        if project_id is not None:
            project = await self.project_repo.get(project_id)
            if project is None:
                raise NotFoundError(f"Project not found: {project_id}")
            if str(project.workspace_id) != str(workspace_id):
                raise PermissionDeniedError("Project is not in the current workspace")

        metadata = _metadata_with_remote_project(metadata, project)
        metadata = session_metadata_with_execution_target(metadata, execution_target)

        return await self.session_repo.create(
            project_id=str(project_id) if project_id else None,
            workspace_id=workspace_id,
            user_id=user_id,
            title=title,
            role_profile=role_profile,
            permission_mode=permission_mode,
            automation_mode=automation_mode,
            default_model_profile_id=default_model_profile_id,
            runtime_mode="api",
            prompt_snapshot=default_system_prompt_snapshot().as_dict(),
            toolset_policy=toolset_policy or EXECUTION_TOOLSET_POLICY,
            context_policy={"memory": "accepted_project_scope", "transcript": "canonical"},
            compression_state={
                "enabled": True,
                "threshold_chars": int(settings.agent_compact_threshold),
                "preserve_recent_messages": 12,
            },
            lineage=lineage if lineage is not None else {"parent_session_id": None},
            session_metadata=session_metadata_with_model_selection(
                metadata, model_selection
            ),
        )

    async def list_sessions(
        self,
        *,
        workspace_id: str,
        user_id: str,
        project_id: str | None = None,
        parent_session_id: str | None = None,
        include_children: bool = False,
    ):
        return await self.session_repo.list_for_user(
            workspace_id=workspace_id,
            user_id=user_id,
            project_id=project_id,
            parent_session_id=parent_session_id,
            include_children=include_children,
        )

    async def require_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        session = await self.session_repo.get(session_id)
        if session is None or session.status == AgentSessionStatus.DELETED:
            raise NotFoundError(f"Agent session not found: {session_id}")
        if str(session.workspace_id) != str(workspace_id) or str(session.user_id) != user_id:
            raise PermissionDeniedError("Agent session is not accessible")
        return session

    async def update_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        updates: dict[str, Any],
    ):
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if "execution_target" in updates:
            next_metadata = session_metadata_with_execution_target(
                getattr(session, "session_metadata", None),
                updates["execution_target"],
            )
            target_changed = (
                session_execution_target_from_metadata(next_metadata)
                != execution_target_from_session(session)
            )
            active_turn_id = getattr(session, "active_turn_id", None)
            if target_changed and active_turn_id is not None:
                active_turn = await self.turn_repo.get_fresh(str(active_turn_id))
                if active_turn is not None and active_turn.status not in {
                    AgentTurnStatus.COMPLETED,
                    AgentTurnStatus.FAILED,
                    AgentTurnStatus.CANCELLED,
                }:
                    raise ConflictError(
                        "Execution target cannot change while an agent turn is active"
                    )
                await self.session_repo.release_active_turn(
                    str(session.id), str(active_turn_id)
                )
                refreshed = await self.session_repo.get_fresh(str(session.id))
                if refreshed is not None:
                    session = refreshed
        update_data: dict[str, Any] = {}
        for key in (
            "title",
            "role_profile",
            "permission_mode",
            "automation_mode",
            "default_model_profile_id",
            "status",
        ):
            if key in updates:
                update_data[key] = updates[key]
        if "mode" in updates and updates["mode"]:
            update_data["toolset_policy"] = {"name": updates["mode"]}
        if (
            "metadata" in updates
            or "model_selection" in updates
            or "execution_target" in updates
        ):
            current_metadata = (
                session.session_metadata if hasattr(session, "session_metadata") else None
            )
            metadata = updates["metadata"] if "metadata" in updates else current_metadata
            execution_target = (
                updates["execution_target"]
                if "execution_target" in updates
                else (current_metadata or {}).get("execution_target")
            )
            metadata = session_metadata_with_execution_target(
                metadata,
                execution_target,
            )
            model_selection = (
                updates["model_selection"]
                if "model_selection" in updates
                else (current_metadata or {}).get("model_selection")
            )
            update_data["session_metadata"] = session_metadata_with_model_selection(
                metadata, model_selection
            )
        return await self.session_repo.update_all(session, **update_data)

    async def delete_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> None:
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        await self.session_repo.update_all(session, status=AgentSessionStatus.DELETED)

    async def create_turn_record(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        input_text: str,
        input_parts: list[dict] | None = None,
        active_skill_names: list[str] | None = None,
        model_profile_id: str | None = None,
        model_selection: dict | None = None,
        execution_target: dict | None = None,
        metadata: dict | None = None,
    ):
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        unresolved_turn = await self.turn_repo.find_with_pending_observation(
            str(session.id)
        )
        unresolved_calls = await AgentTranscriptStore(self.db).unresolved_tool_calls(
            str(session.id)
        )
        if unresolved_turn is not None or unresolved_calls:
            raise ConflictError(
                "Cannot create a new turn while a prior turn has unresolved tool calls"
            )
        normalized_active_skill_names = _validated_active_skill_names(active_skill_names)
        turn_metadata = _metadata_with_active_skill_names(
            metadata,
            normalized_active_skill_names,
        )
        if execution_target is not None:
            turn_metadata = session_metadata_with_execution_target(
                turn_metadata,
                execution_target,
            )
        transcript_parts = _transcript_parts_for_turn(
            input_text=input_text,
            input_parts=input_parts,
        )
        session_updates: dict[str, object] = {}
        if execution_target is not None:
            session_updates["session_metadata"] = session_metadata_with_execution_target(
                getattr(session, "session_metadata", None),
                execution_target,
            )
        if not session.title and not await self.turn_repo.list_for_session(str(session.id)):
            session_updates["title"] = _generated_session_title(input_text)
        normalized_model_selection = normalize_model_selection(model_selection)
        turn_id = str(uuid4())
        turn = await self.turn_repo.create_with_session_claim(
            session_id=str(session.id),
            turn_id=turn_id,
            session_updates=session_updates,
            user_parts=transcript_parts,
            user_metadata={"turn_id": turn_id},
            created_event_type=AgentEventType.TURN_CREATED,
            created_event_payload={"input_text": input_text},
            project_id=str(session.project_id) if session.project_id else None,
            workspace_id=str(session.workspace_id),
            user_id=user_id,
            input_text=input_text,
            input_parts=input_parts,
            status=AgentTurnStatus.QUEUED,
            model_profile_snapshot={
                "requested_model_profile_id": model_profile_id,
                "requested_model_selection": normalized_model_selection,
                "metadata": turn_metadata,
            },
            budget_snapshot={"max_iterations": 0, "used_iterations": 0},
            loop_state={"state": "queued"},
        )
        if turn is None:
            raise ConflictError(
                "Cannot create a new turn while another turn is active in this session"
            )
        await self.db.refresh(session)
        return turn

    async def create_turn(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        input_text: str,
        input_parts: list[dict] | None = None,
        active_skill_names: list[str] | None = None,
        model_profile_id: str | None = None,
        model_selection: dict | None = None,
        execution_target: dict | None = None,
        metadata: dict | None = None,
    ):
        turn = await self.create_turn_record(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            input_text=input_text,
            input_parts=input_parts,
            active_skill_names=active_skill_names,
            model_profile_id=model_profile_id,
            model_selection=model_selection,
            execution_target=execution_target,
            metadata=metadata,
        )
        enqueue_turn_run(str(turn.id), str(turn.session_id))
        return turn

    async def list_turns(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.turn_repo.list_for_session(session_id)

    async def require_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            raise NotFoundError(f"Agent turn not found: {turn_id}")
        await self.require_session(
            session_id=str(turn.session_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return turn

    async def cancel_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        now = datetime.now(timezone.utc)
        cancelled_in_runner = cancel_turn_run(str(turn.id))
        updated = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.CANCELLED,
            termination_reason="cancelled",
            completed_at=now,
            loop_state={
                **dict(getattr(turn, "loop_state", None) or {}),
                "termination_reason": "cancelled",
            },
            claimed_at=None,
            lease_until=None,
        )
        await self._cancel_open_actions(str(turn.id), cancelled_at=now)
        updated = await self.turn_repo.update_all(
            updated,
            loop_state={"termination_reason": "cancelled"},
        )
        await self.session_repo.release_active_turn(
            str(updated.session_id), str(updated.id)
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_CANCELLED,
            payload={"task_cancelled": cancelled_in_runner},
        )
        return updated

    async def interrupt_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        now = datetime.now(timezone.utc)
        cancelled_in_runner = cancel_turn_run(str(turn.id))
        updated = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.CANCELLED,
            interrupt_requested_at=now,
            termination_reason="interrupted",
            completed_at=now,
            loop_state={
                **dict(getattr(turn, "loop_state", None) or {}),
                "termination_reason": "interrupted",
            },
            claimed_at=None,
            lease_until=None,
        )
        await self._cancel_open_actions(str(turn.id), cancelled_at=now)
        updated = await self.turn_repo.update_all(
            updated,
            loop_state={"termination_reason": "interrupted"},
        )
        await self.session_repo.release_active_turn(
            str(updated.session_id), str(updated.id)
        )
        await self.ledger.append(
            session_id=str(updated.session_id),
            turn_id=str(updated.id),
            type=AgentEventType.TURN_INTERRUPTED,
            payload={
                "termination_reason": "interrupted",
                "task_cancelled": cancelled_in_runner,
            },
        )
        return updated

    async def list_events_for_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
        after_seq: int = 0,
    ):
        await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.event_repo.list_for_turn(turn_id=turn_id, after_seq=after_seq)

    async def list_events_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        after_seq: int = 0,
        limit: int | None = None,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.event_repo.list_for_session(
            session_id=session_id,
            after_seq=after_seq,
            limit=limit,
        )

    async def decide_action(
        self,
        *,
        action_id: str,
        workspace_id: str,
        user_id: str,
        decision: str,
        note: str | None = None,
        modified_input: dict | None = None,
        answer: dict | None = None,
    ):
        action = await self.action_repo.get(action_id)
        if action is None:
            raise NotFoundError(f"Agent action not found: {action_id}")
        await self.require_turn(
            turn_id=str(action.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if action.status != AgentActionStatus.WAITING_DECISION:
            raise ConflictError(f"Agent action is not waiting for a decision: {action.status}")

        next_input = action.input
        if decision == "modify":
            if modified_input is None:
                raise BadRequestError("modified_input is required when decision is modify")
            next_input = modified_input
        elif decision == "answer":
            # Thread the user's reply back into the tool input under a reserved
            # key; ask_user echoes it as the tool result on resume.
            next_input = {**(action.input or {}), "_user_answer": answer or {}}

        status = (
            AgentActionStatus.REJECTED
            if decision == "reject"
            else AgentActionStatus.REQUESTED
        )
        updated = await self.action_repo.transition_if_status(
            str(action.id),
            expected_statuses=[AgentActionStatus.WAITING_DECISION],
            status=status,
            input=next_input,
            normalized_input=next_input,
            redacted_input=next_input,
            permission_decision={
                "decision": decision,
                "note": note,
                "modified_input": modified_input,
                "answer": answer,
            },
        )
        if updated is None:
            raise ConflictError("Agent action changed before the decision was recorded")
        # Enable execution only after the approval transition wins its race.
        if decision == "approve" and action.name == "exit_plan_mode":
            await self._activate_execution_toolset(str(action.session_id))
        await self.ledger.append(
            session_id=str(action.session_id),
            turn_id=str(action.turn_id),
            type=AgentEventType.ACTION_DECISION_RECORDED,
            payload={
                "action_id": str(action.id),
                "decision": decision,
                "note": note,
                **({"answer": answer} if decision == "answer" else {}),
            },
        )
        if decision in {"approve", "modify", "reject", "answer"} and updated.kind == "tool":
            enqueue_turn_resume(
                str(updated.id), str(updated.turn_id), str(updated.session_id)
            )
        return updated

    async def _activate_execution_toolset(self, session_id: str) -> None:
        session = await self.session_repo.get(session_id)
        if session is None:
            return
        await self.session_repo.update_all(session, toolset_policy=EXECUTION_TOOLSET_POLICY)

    async def resume_action(
        self,
        *,
        action_id: str,
        workspace_id: str,
        user_id: str,
    ):
        action = await self.action_repo.get(action_id)
        if action is None:
            raise NotFoundError(f"Agent action not found: {action_id}")
        turn = await self.require_turn(
            turn_id=str(action.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if action.status not in {
            AgentActionStatus.REQUESTED,
            AgentActionStatus.REJECTED,
        }:
            raise ConflictError(
                f"Agent action cannot resume from status: {action.status}"
            )
        if not action_matches_pending_observation(turn, action):
            raise ConflictError("Agent action is not the turn's pending observation")
        enqueue_turn_resume(str(action.id), str(action.turn_id), str(turn.session_id))
        return action

    async def recover_orphaned_turns(self) -> dict[str, int]:
        summary = {"enqueued": 0, "failed": 0, "waiting": 0, "skipped": 0}
        for turn in await self.turn_repo.list_recoverable():
            if is_turn_running(str(turn.id)) or _turn_lease_is_active(turn):
                summary["skipped"] += 1
                continue
            outcome = await self._recover_turn(str(turn.id))
            summary[outcome] = summary.get(outcome, 0) + 1
        return summary

    async def _recover_turn(self, turn_id: str) -> str:
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            return "skipped"
        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            await self.session_repo.release_active_turn(
                str(turn.session_id), str(turn.id)
            )
            return "skipped"
        if _turn_lease_is_active(turn):
            return "skipped"
        recovery_now = datetime.now(timezone.utc)
        recovered_turn = await self.turn_repo.claim_for_recovery(
            str(turn.id),
            expected_status=turn.status,
            expected_claimed_at=turn.claimed_at,
            claimed_at=recovery_now,
            lease_until=recovery_now + _recovery_lease_duration(),
        )
        if recovered_turn is None:
            return "skipped"
        turn = recovered_turn
        recovery_claimed_at = turn.claimed_at
        if not await self.session_repo.claim_active_turn(
            str(turn.session_id), str(turn.id)
        ):
            return "skipped"

        turn = await self._reconcile_pending_observation(
            turn, claim_token=recovery_claimed_at
        )

        open_actions = await self.action_repo.list_open_for_turn(turn_id)
        latest_action = open_actions[0] if open_actions else None
        now = datetime.now(timezone.utc)

        if latest_action is not None and latest_action.status == AgentActionStatus.WAITING_DECISION:
            updated_turn = await self._update_recovery_turn(
                turn,
                claim_token=recovery_claimed_at,
                status=AgentTurnStatus.WAITING_APPROVAL,
                claimed_at=None,
                lease_until=None,
                completed_at=None,
                loop_state=_recovery_loop_state(
                    turn,
                    state="waiting_approval",
                    recovered=True,
                ),
            )
            if updated_turn is None:
                return "skipped"
            return "waiting"

        if latest_action is not None and latest_action.status == AgentActionStatus.REQUESTED:
            updated_turn = await self._update_recovery_turn(
                turn,
                claim_token=recovery_claimed_at,
                status=AgentTurnStatus.QUEUED,
                completed_at=None,
                error_code=None,
                error_message=None,
                claimed_at=None,
                lease_until=None,
                loop_state=_recovery_loop_state(
                    turn,
                    state="queued",
                    recovered=True,
                    resume_action_id=str(latest_action.id),
                ),
            )
            if updated_turn is None:
                return "skipped"
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_RECOVERY_ENQUEUED,
                payload={"mode": "resume", "action_id": str(latest_action.id)},
            )
            enqueue_turn_resume(
                str(latest_action.id), str(turn.id), str(turn.session_id)
            )
            return "enqueued"

        if latest_action is not None and latest_action.status == AgentActionStatus.RUNNING:
            await self._cancel_open_actions(turn_id, cancelled_at=now)
            failed_turn = await self._update_recovery_turn(
                turn,
                claim_token=recovery_claimed_at,
                status=AgentTurnStatus.FAILED,
                termination_reason="model_failed",
                error_code="recovery_inflight_action",
                error_message="Agent process stopped while a tool action was running.",
                completed_at=now,
                claimed_at=None,
                lease_until=None,
                loop_state=_recovery_loop_state(
                    turn,
                    termination_reason="model_failed",
                    recovered=True,
                ),
            )
            if failed_turn is None:
                return "skipped"
            await self.session_repo.release_active_turn(
                str(failed_turn.session_id), str(failed_turn.id)
            )
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_RECOVERY_FAILED,
                payload={"error_code": "recovery_inflight_action"},
            )
            return "failed"

        for unresolved_call in await AgentTranscriptStore(
            self.db
        ).unresolved_tool_calls(str(turn.session_id), turn_id=str(turn.id)):
            await AgentTranscriptStore(self.db).append_tool_result_once(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                tool_call_id=unresolved_call["tool_call_id"],
                tool_name=unresolved_call["tool_name"],
                status="failed",
                error={
                    "type": "RecoveryInterruptedToolCall",
                    "message": (
                        "The agent process stopped before this tool call produced a result."
                    ),
                },
            )

        queued_turn = await self._update_recovery_turn(
            turn,
            claim_token=recovery_claimed_at,
            status=AgentTurnStatus.QUEUED,
            termination_reason=None,
            completed_at=None,
            error_code=None,
            error_message=None,
            claimed_at=None,
            lease_until=None,
            loop_state=_recovery_loop_state(
                turn,
                state="queued",
                recovered=True,
            ),
        )
        if queued_turn is None:
            return "skipped"
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_RECOVERY_ENQUEUED,
            payload={"mode": "run"},
        )
        enqueue_turn_run(str(turn.id), str(turn.session_id))
        return "enqueued"

    async def _update_recovery_turn(
        self,
        turn,
        *,
        claim_token,
        **values,
    ):
        return await self.turn_repo.update_if_recovery_claimed(
            str(turn.id),
            expected_claimed_at=claim_token,
            **values,
        )

    async def _cancel_open_actions(self, turn_id: str, *, cancelled_at: datetime) -> None:
        for action in await self.action_repo.list_open_for_turn(turn_id):
            updated = await self.action_repo.transition_if_status(
                str(action.id),
                expected_statuses=[
                    AgentActionStatus.WAITING_DECISION,
                    AgentActionStatus.REQUESTED,
                    AgentActionStatus.RUNNING,
                ],
                status=AgentActionStatus.CANCELLED,
                error={"type": "CancelledError", "message": "Action cancelled with its parent turn."},
                completed_at=cancelled_at,
                requires_resume=False,
            )
            if updated is None:
                continue
            await AgentTranscriptStore(self.db).append_tool_result_once(
                session_id=str(updated.session_id),
                turn_id=str(updated.turn_id),
                tool_call_id=updated.tool_call_id,
                tool_name=updated.name,
                status=updated.status,
                result=updated.result,
                error=updated.error,
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={"action_id": str(action.id), "tool": action.name},
            )
        turn = await self.turn_repo.get(turn_id)
        if turn is None:
            return
        progress = ((getattr(turn, "loop_state", None) or {}).get("progress") or {})
        pending = progress.get("pending_observation")
        if isinstance(pending, dict):
            for deferred in pending.get("deferred_tool_calls") or []:
                if not isinstance(deferred, dict):
                    continue
                await AgentTranscriptStore(self.db).append_tool_result_once(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    tool_call_id=str(deferred.get("tool_call_id") or ""),
                    tool_name=str(deferred.get("tool_name") or ""),
                    status="deferred",
                    error={
                        "type": "DeferredToolCall",
                        "message": "Tool call was deferred because its parent turn was cancelled.",
                    },
                )
        transcript = AgentTranscriptStore(self.db)
        for unresolved in await transcript.unresolved_tool_calls(
            str(turn.session_id), turn_id=str(turn.id)
        ):
            await transcript.append_tool_result_once(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                tool_call_id=unresolved["tool_call_id"],
                tool_name=unresolved["tool_name"],
                status=AgentActionStatus.CANCELLED,
                error={
                    "type": "CancelledError",
                    "message": "Tool call was cancelled with its parent turn.",
                },
            )

    async def _reconcile_pending_observation(self, turn, *, claim_token=None):
        loop_state = dict(getattr(turn, "loop_state", None) or {})
        progress = dict(loop_state.get("progress") or {})
        pending = progress.get("pending_observation")
        if not isinstance(pending, dict):
            return turn
        pending_results = list(pending.get("tool_results") or [])
        actions = await self.action_repo.list_for_turn(str(turn.id))
        terminal_statuses = {
            AgentActionStatus.COMPLETED,
            AgentActionStatus.FAILED,
            AgentActionStatus.CANCELLED,
            AgentActionStatus.REJECTED,
        }
        matched_action = None
        matched_index = -1
        for index, signature in enumerate(pending_results):
            try:
                descriptor = json.loads(signature)
            except (TypeError, json.JSONDecodeError):
                continue
            if descriptor.get("status") != "pending":
                continue
            call_id = str(descriptor.get("tool_call_id") or "")
            matched_action = next(
                (
                    action
                    for action in actions
                    if str(action.tool_call_id or "") == call_id
                    and action.status in terminal_statuses
                ),
                None,
            )
            if matched_action is not None:
                matched_index = index
                break
        if matched_action is None:
            return turn

        error = matched_action.error
        if matched_action.status == AgentActionStatus.REJECTED and not error:
            error = {
                "type": "UserRejected",
                "message": "The user rejected this tool call.",
            }
        await AgentTranscriptStore(self.db).append_tool_result_once(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            tool_call_id=matched_action.tool_call_id,
            tool_name=matched_action.name,
            status=matched_action.status,
            result=matched_action.result,
            error=error,
        )
        pending_results[matched_index] = _recovery_result_signature(
            tool_name=matched_action.name,
            status=matched_action.status,
            result=matched_action.result,
            error=error,
        )
        for deferred in pending.get("deferred_tool_calls") or []:
            if not isinstance(deferred, dict):
                continue
            await AgentTranscriptStore(self.db).append_tool_result_once(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                tool_call_id=str(deferred.get("tool_call_id") or ""),
                tool_name=str(deferred.get("tool_name") or ""),
                status="deferred",
                error={
                    "type": "DeferredToolCall",
                    "message": "Tool call was deferred by an earlier approval boundary.",
                },
            )
        progress["previous_tool_calls"] = list(pending.get("tool_calls") or [])
        progress["previous_tool_results"] = pending_results
        progress.pop("pending_observation", None)
        loop_state["progress"] = progress
        updated = await self.turn_repo.update_if_recovery_claimed(
            str(turn.id),
            expected_claimed_at=claim_token,
            loop_state=loop_state,
        )
        return updated or await self.turn_repo.get_fresh(str(turn.id))

    async def list_artifacts_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ):
        await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.artifact_repo.list_for_session(session_id)

    async def list_artifacts_for_turn(
        self,
        *,
        turn_id: str,
        workspace_id: str,
        user_id: str,
    ):
        turn = await self.require_turn(
            turn_id=turn_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return await self.artifact_repo.list_for_turn(str(turn.id))

    async def get_artifact(
        self,
        *,
        artifact_id: str,
        workspace_id: str,
        user_id: str,
    ):
        artifact = await self.artifact_repo.get(artifact_id)
        if artifact is None:
            raise NotFoundError(f"Agent artifact not found: {artifact_id}")
        await self.require_turn(
            turn_id=str(artifact.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return artifact


def _metadata_with_remote_project(metadata: dict | None, project) -> dict | None:
    if not project or getattr(project, "storage_mode", None) != "remote":
        return metadata
    connection_id = getattr(project, "remote_connection_id", None)
    remote_root_path = getattr(project, "remote_root_path", None)
    if not connection_id or not remote_root_path:
        return metadata
    merged = dict(metadata or {})
    merged["remote_connection_id"] = str(connection_id)
    merged["remote_project_id"] = str(project.id)
    merged["remote_project_root"] = str(remote_root_path)
    return merged


def _recovery_result_signature(
    *,
    tool_name: str,
    status: str,
    result: dict | None,
    error: dict | None,
) -> str:
    return json.dumps(
        {
            "tool": tool_name,
            "status": status,
            "result": result,
            "error": error,
        },
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )


def _metadata_with_active_skill_names(
    metadata: dict | None,
    active_skill_names: list[str],
) -> dict:
    merged = dict(metadata or {})
    if active_skill_names:
        merged["active_skill_names"] = active_skill_names
    else:
        merged.pop("active_skill_names", None)
    return merged


def _validated_active_skill_names(values: list[str] | None) -> list[str]:
    try:
        names = normalize_skill_names(values)
        if not names:
            return []
        resolve_active_skills(AgentSkillRegistry.from_default_roots(), names)
        return names
    except ActiveSkillResolutionError as exc:
        raise BadRequestError(str(exc)) from exc
    except ValueError as exc:
        raise BadRequestError(str(exc)) from exc


def _generated_session_title(input_text: str) -> str:
    compact = " ".join(input_text.strip().split())
    if not compact:
        return "New conversation"
    compact = compact.strip("'\"`*_#> ")
    if len(compact) <= 30:
        return compact
    candidate = compact[:30].rstrip(" ,.;:，。；：")
    if " " in candidate:
        boundary = candidate.rfind(" ")
        if boundary >= 12:
            candidate = candidate[:boundary]
    if not candidate:
        return compact[:30]
    return candidate


_FILE_REF_MAX_BYTES = 64 * 1024
_DENIED_CONTEXT_NAMES = {
    ".env",
    "better-auth.db",
    "bioinfoflow.db",
    "id_dsa",
    "id_ecdsa",
    "id_ed25519",
    "id_rsa",
}
_DENIED_CONTEXT_SUFFIXES = {".db", ".sqlite", ".sqlite3"}
_WORKFLOW_REF_ALLOWED_KEYS = frozenset(
    {
        "kind",
        "type",
        "workflow_id",
        "project_id",
        "scope",
    }
)
_WORKFLOW_REF_SCOPES = frozenset({"project", "global"})
_WORKFLOW_REF_MAX_FIELD_LENGTH = 256


def _transcript_parts_for_turn(*, input_text: str, input_parts: list[dict] | None) -> list[dict]:
    if not input_parts:
        return [text_part(input_text)]

    parts: list[dict] = []
    has_text_part = False
    for part in input_parts:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            text = part["text"]
            if text.strip():
                has_text_part = True
                parts.append(text_part(text))
            continue
        if part.get("kind") == "file_ref" or part.get("type") == "file_ref":
            parts.append(text_part(_file_ref_text(part)))
            continue
        if part.get("kind") == "workflow_ref" or part.get("type") == "workflow_ref":
            parts.append(text_part(_workflow_ref_text(part)))
    if not has_text_part and input_text.strip():
        parts.insert(0, text_part(input_text))
    return parts or [text_part(input_text)]


def _file_ref_text(part: dict) -> str:
    path = part.get("path")
    if not isinstance(path, str) or not path.strip():
        raise BadRequestError("file_ref input part requires a path")
    target = FilesystemPolicy().require_allowed_path(
        path, must_exist=True, allow_directory=False
    )
    if _is_sensitive_context_path(target):
        raise PermissionDeniedError(f"File cannot be attached to agent context: {target}")

    label = str(part.get("label") or target.name)
    if part.get("includeContent") is False:
        return f"Attached file reference: {label}\nPath: {target}\nContent: not included."

    size = target.stat().st_size
    with target.open("rb") as file:
        raw = file.read(_FILE_REF_MAX_BYTES + 1)
    truncated = size > _FILE_REF_MAX_BYTES or len(raw) > _FILE_REF_MAX_BYTES
    raw = raw[:_FILE_REF_MAX_BYTES]
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise BadRequestError("Attached file is not valid UTF-8 text") from exc

    suffix = "\n[File truncated]" if truncated else ""
    return f"Attached file: {label}\nPath: {target}\n\n{content}{suffix}"


def _workflow_ref_text(part: dict) -> str:
    _validate_workflow_ref_keys(part)
    workflow_id = _optional_workflow_ref_string(part, "workflow_id")
    project_id = _optional_workflow_ref_string(part, "project_id")
    scope = _optional_workflow_ref_string(part, "scope")

    if not any([workflow_id, project_id, scope]):
        raise BadRequestError(
            "workflow_ref input part requires a workflow_id, project_id, or scope"
        )
    if scope and scope not in _WORKFLOW_REF_SCOPES:
        raise BadRequestError("workflow_ref scope must be project or global")

    lines = [f"Workflow context: {_workflow_ref_label(scope=scope, project_id=project_id)}"]
    if workflow_id:
        lines.append(f"Workflow ID: {workflow_id}")
    if project_id:
        lines.append(f"Project ID: {project_id}")
    elif scope == "global":
        lines.append("Scope: all registered workflows")
    lines.append(
        "Use workflow tools such as workflows.get, workflows.form_spec, "
        "workflows.dag, workflows.source, runs.list, and runs.submit as needed "
        "before acting."
    )
    return "\n".join(lines)


def _workflow_ref_label(*, scope: str, project_id: str) -> str:
    if project_id or scope == "project":
        return "Project workflows"
    if scope == "global":
        return "All registered workflows"
    return "Workflow context"


def _validate_workflow_ref_keys(part: dict) -> None:
    unsupported = sorted(set(part) - _WORKFLOW_REF_ALLOWED_KEYS)
    if unsupported:
        raise BadRequestError(
            "workflow_ref input part has unsupported fields: "
            + ", ".join(unsupported)
        )
    for discriminator in ("kind", "type"):
        value = part.get(discriminator)
        if value is not None and value != "workflow_ref":
            raise BadRequestError(f"workflow_ref {discriminator} must be workflow_ref")


def _optional_workflow_ref_string(part: dict, key: str) -> str:
    value = part.get(key)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise BadRequestError(f"workflow_ref {key} must be a string")
    normalized = value.strip()
    if not normalized:
        return ""
    if "\n" in normalized or "\r" in normalized:
        raise BadRequestError(f"workflow_ref {key} must be a single line")
    if len(normalized) > _WORKFLOW_REF_MAX_FIELD_LENGTH:
        raise BadRequestError(
            f"workflow_ref {key} must be at most "
            f"{_WORKFLOW_REF_MAX_FIELD_LENGTH} characters"
        )
    return normalized


def _is_sensitive_context_path(path) -> bool:
    name = path.name.lower()
    if name in _DENIED_CONTEXT_NAMES:
        return True
    if name.startswith(".env."):
        return True
    return path.is_file() and path.suffix.lower() in _DENIED_CONTEXT_SUFFIXES


def _recovery_loop_state(turn, **updates: Any) -> dict[str, Any]:
    loop_state = dict(getattr(turn, "loop_state", None) or {})
    loop_state.update(updates)
    return loop_state


def _turn_lease_is_active(turn) -> bool:
    if getattr(turn, "status", None) != AgentTurnStatus.RUNNING:
        return False
    lease_until = getattr(turn, "lease_until", None)
    if lease_until is None:
        return False
    now = datetime.now(timezone.utc)
    if lease_until.tzinfo is None:
        now = now.replace(tzinfo=None)
    return lease_until > now


def _recovery_lease_duration() -> timedelta:
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)
