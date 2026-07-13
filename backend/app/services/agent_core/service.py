from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

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
    normalize_execution_target,
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
        previous_authorization = _authorization_state(session)
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
        next_authorization = _authorization_state(
            session,
            role_profile=update_data.get("role_profile", session.role_profile),
            permission_mode=update_data.get("permission_mode", session.permission_mode),
            automation_mode=update_data.get("automation_mode", session.automation_mode),
            toolset_policy=update_data.get("toolset_policy", session.toolset_policy),
            session_metadata=update_data.get(
                "session_metadata", session.session_metadata
            ),
        )
        return await self.session_repo.update_with_policy_version(
            session,
            increment_policy_version=previous_authorization != next_authorization,
            **update_data,
        )

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
        if execution_target is not None:
            previous_target = execution_target_from_session(session)
            next_metadata = session_metadata_with_execution_target(
                getattr(session, "session_metadata", None),
                execution_target,
            )
            session = await self.session_repo.update_with_policy_version(
                session,
                increment_policy_version=(
                    previous_target
                    != normalize_execution_target(None, metadata=next_metadata)
                ),
                session_metadata=next_metadata,
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
        if not session.title and not await self.turn_repo.list_for_session(str(session.id)):
            session = await self.session_repo.update_all(
                session,
                title=_generated_session_title(input_text),
            )
        normalized_model_selection = normalize_model_selection(model_selection)
        turn = await self.turn_repo.create(
            session_id=str(session.id),
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
        await AgentTranscriptStore(self.db).append_parts(
            session_id=str(session.id),
            turn_id=str(turn.id),
            role="user",
            parts=transcript_parts,
            metadata={"turn_id": str(turn.id)},
        )
        await self.ledger.append(
            session_id=str(session.id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_CREATED,
            payload={"input_text": input_text},
        )
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
        await self._cancel_open_actions(str(turn.id), cancelled_at=now)
        updated = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.CANCELLED,
            termination_reason="cancelled",
            completed_at=now,
            loop_state={"termination_reason": "cancelled"},
            claimed_at=None,
            lease_until=None,
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
        await self._cancel_open_actions(str(turn.id), cancelled_at=now)
        updated = await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.CANCELLED,
            interrupt_requested_at=now,
            termination_reason="interrupted",
            completed_at=now,
            loop_state={"termination_reason": "interrupted"},
            claimed_at=None,
            lease_until=None,
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

        # When a plan is approved, flip the session into the execution toolset
        # *before* enqueueing resume — the resume worker reads the session
        # toolset fresh, so the model gains write/exec tools on the next round.
        if decision == "approve" and action.name == "exit_plan_mode":
            await self._activate_execution_toolset(str(action.session_id))

        status = (
            AgentActionStatus.REJECTED
            if decision == "reject"
            else AgentActionStatus.REQUESTED
        )
        updated = await self.action_repo.update_all(
            action,
            input=next_input,
            normalized_input=next_input,
            redacted_input=next_input,
            permission_decision={
                "decision": decision,
                "note": note,
                "evaluated_policy_version": action.evaluated_policy_version,
                "modified_input": modified_input,
                "answer": answer,
            },
            status=status,
        )
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
        session = await self.session_repo.get_fresh(session_id)
        if session is None:
            return
        await self.session_repo.update_with_policy_version(
            session,
            increment_policy_version=(
                _normalized_toolset(session.toolset_policy)
                != _normalized_toolset(EXECUTION_TOOLSET_POLICY)
            ),
            toolset_policy=EXECUTION_TOOLSET_POLICY,
        )

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
        enqueue_turn_resume(str(action.id), str(action.turn_id), str(turn.session_id))
        return action

    async def get_action(
        self,
        *,
        action_id: str,
        workspace_id: str,
        user_id: str,
    ):
        action = await self.action_repo.get(action_id)
        if action is None:
            raise NotFoundError(f"Agent action not found: {action_id}")
        await self.require_turn(
            turn_id=str(action.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return action

    async def recover_orphaned_turns(self) -> dict[str, int]:
        summary = {"enqueued": 0, "failed": 0, "waiting": 0, "skipped": 0}
        for turn in await self.turn_repo.list_recoverable():
            if is_turn_running(str(turn.id)):
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
            return "skipped"

        open_actions = await self.action_repo.list_open_for_turn(turn_id)
        latest_action = open_actions[0] if open_actions else None
        now = datetime.now(timezone.utc)

        if latest_action is not None and latest_action.status == AgentActionStatus.WAITING_DECISION:
            await self.turn_repo.update_all(
                turn,
                status=AgentTurnStatus.WAITING_APPROVAL,
                claimed_at=None,
                lease_until=None,
                completed_at=None,
                loop_state={"state": "waiting_approval", "recovered": True},
            )
            return "waiting"

        if latest_action is not None and latest_action.status == AgentActionStatus.REQUESTED:
            await self.turn_repo.update_all(
                turn,
                status=AgentTurnStatus.RUNNING,
                completed_at=None,
                error_code=None,
                error_message=None,
                claimed_at=None,
                lease_until=None,
                loop_state={"state": "running", "recovered": True, "resume_action_id": str(latest_action.id)},
            )
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
            await self.turn_repo.update_all(
                turn,
                status=AgentTurnStatus.FAILED,
                termination_reason="model_failed",
                error_code="recovery_inflight_action",
                error_message="Agent process stopped while a tool action was running.",
                completed_at=now,
                claimed_at=None,
                lease_until=None,
                loop_state={"termination_reason": "model_failed", "recovered": True},
            )
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_RECOVERY_FAILED,
                payload={"error_code": "recovery_inflight_action"},
            )
            return "failed"

        await self.turn_repo.update_all(
            turn,
            status=AgentTurnStatus.QUEUED,
            termination_reason=None,
            completed_at=None,
            error_code=None,
            error_message=None,
            claimed_at=None,
            lease_until=None,
            loop_state={"state": "queued", "recovered": True},
        )
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_RECOVERY_ENQUEUED,
            payload={"mode": "run"},
        )
        enqueue_turn_run(str(turn.id), str(turn.session_id))
        return "enqueued"

    async def _cancel_open_actions(self, turn_id: str, *, cancelled_at: datetime) -> None:
        for action in await self.action_repo.list_open_for_turn(turn_id):
            await self.action_repo.update_all(
                action,
                status=AgentActionStatus.CANCELLED,
                error={"type": "CancelledError", "message": "Action cancelled with its parent turn."},
                completed_at=cancelled_at,
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={"action_id": str(action.id), "tool": action.name},
            )

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


_UNSET = object()


def _authorization_state(
    session,
    *,
    role_profile: Any = _UNSET,
    permission_mode: Any = _UNSET,
    automation_mode: Any = _UNSET,
    toolset_policy: Any = _UNSET,
    session_metadata: Any = _UNSET,
) -> tuple[Any, ...]:
    metadata = (
        session.session_metadata
        if session_metadata is _UNSET
        else session_metadata
    )
    return (
        str(session.role_profile if role_profile is _UNSET else role_profile),
        str(
            session.permission_mode
            if permission_mode is _UNSET
            else permission_mode
        ),
        str(
            session.automation_mode
            if automation_mode is _UNSET
            else automation_mode
        ),
        _normalized_toolset(
            session.toolset_policy if toolset_policy is _UNSET else toolset_policy
        ),
        tuple(sorted(normalize_execution_target(None, metadata=metadata).items())),
    )


def _normalized_toolset(policy: Any) -> tuple[str, tuple[str, ...] | None]:
    source = policy if isinstance(policy, dict) else {}
    name = str(source.get("name") or "default").strip().lower()
    allowed_tools = source.get("allowed_tools")
    normalized_allowed = (
        tuple(sorted({str(tool) for tool in allowed_tools if str(tool)}))
        if isinstance(allowed_tools, list) and allowed_tools
        else None
    )
    return name, normalized_allowed


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
