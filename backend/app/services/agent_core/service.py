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
    AgentToolCallBatchRepository,
)
from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.execution_target import (
    normalize_execution_scope,
    execution_target_from_session,
    normalize_execution_target,
    session_execution_scope_from_metadata,
    session_metadata_with_execution_scope,
    session_metadata_with_execution_target,
    session_metadata_without_execution_target,
)
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_metadata_with_model_selection,
)
from app.services.agent_core.ownership import new_turn_owner_token
from app.services.agent_core.permissions.remote_boundary import RemoteBoundaryResolver
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
from app.services.agent_core.tools.batches import ToolCallBatchCoordinator
from app.services.agent_core.transcript import AgentTranscriptStore, text_part
from app.utils.exceptions import (
    BadRequestError,
    ConflictError,
    NotFoundError,
    PermissionDeniedError,
)


class AgentCoreService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.session_repo = AgentSessionRepository(session)
        self.turn_repo = AgentTurnRepository(session)
        self.event_repo = AgentEventRepository(session)
        self.action_repo = AgentActionRepository(session)
        self.tool_batch_repo = AgentToolCallBatchRepository(session)
        self.artifact_repo = AgentArtifactRepository(session)
        self.project_repo = ProjectRepository(session)
        self.ledger = AgentEventLedger(session)
        self.runtime = AgentCoreRuntime(session)
        self.transcript = AgentTranscriptStore(session)

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
        execution_scope: dict | None = None,
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
        metadata = session_metadata_with_execution_scope(metadata, execution_scope)

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
            context_policy={
                "memory": "accepted_project_scope",
                "transcript": "canonical",
            },
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
        if (
            str(session.workspace_id) != str(workspace_id)
            or str(session.user_id) != user_id
        ):
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
        pending_strategy = updates.pop("pending_strategy", "future_only")
        session = await self.session_repo.lock_policy(session_id)
        if session is None or session.status == AgentSessionStatus.DELETED:
            raise NotFoundError(f"Agent session not found: {session_id}")
        if (
            str(session.workspace_id) != str(workspace_id)
            or str(session.user_id) != user_id
        ):
            raise PermissionDeniedError("Agent session is not accessible")
        previous_authorization = _authorization_state(
            session,
            remote_boundary_fingerprint=await _remote_boundary_fingerprint(
                self.db,
                session=session,
                session_metadata=session.session_metadata,
            ),
        )
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
            or "execution_scope" in updates
        ):
            current_metadata = (
                session.session_metadata
                if hasattr(session, "session_metadata")
                else None
            )
            metadata = (
                updates["metadata"] if "metadata" in updates else current_metadata
            )
            if "execution_target" in updates:
                execution_target = updates["execution_target"]
                if execution_target is None:
                    metadata = session_metadata_without_execution_target(
                        metadata,
                        clear_remote_alias=True,
                    )
                else:
                    metadata = session_metadata_with_execution_target(
                        metadata,
                        execution_target,
                    )
            else:
                execution_target = (current_metadata or {}).get("execution_target")
                if "execution_scope" in updates:
                    normalized_scope = normalize_execution_scope(
                        updates["execution_scope"]
                    )
                    metadata = session_metadata_without_execution_target(
                        metadata,
                        clear_remote_alias=normalized_scope is not None
                        and normalized_scope.get("mode") == "auto",
                    )
                else:
                    metadata = session_metadata_with_execution_target(
                        metadata,
                        execution_target,
                    )
            execution_scope = (
                updates["execution_scope"]
                if "execution_scope" in updates
                else (current_metadata or {}).get("execution_scope")
            )
            metadata = session_metadata_with_execution_scope(
                metadata,
                execution_scope,
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
            remote_boundary_fingerprint=await _remote_boundary_fingerprint(
                self.db,
                session=session,
                session_metadata=update_data.get(
                    "session_metadata", session.session_metadata
                ),
            ),
        )
        policy_changed = previous_authorization != next_authorization
        target_changed = (
            "session_metadata" in update_data
            and normalize_execution_target(
                None, metadata=update_data["session_metadata"]
            )
            != execution_target_from_session(session)
        )
        scope_changed = (
            "session_metadata" in update_data
            and _normalized_execution_scope(update_data["session_metadata"])
            != _normalized_execution_scope(session.session_metadata)
        )
        wakeups: list[tuple[str, str, str]] = []
        reconciliation = {
            "affected_count": 0,
            "excluded_count": 0,
            "already_resolved_count": 0,
        }
        try:
            if update_data or policy_changed:
                updated = await self.session_repo.update_with_policy_version(
                    session,
                    increment_policy_version=policy_changed,
                    require_target_mutable=target_changed or scope_changed,
                    commit=False,
                    **update_data,
                )
                if updated is None:
                    raise ConflictError(
                        "Execution target or scope cannot change while an agent "
                        "turn is active"
                    )
            else:
                updated = await self.session_repo.get_fresh(str(session.id))
                if updated is None:
                    raise NotFoundError(f"Agent session not found: {session.id}")

            if policy_changed:
                await self.ledger.append(
                    session_id=str(updated.id),
                    turn_id=None,
                    type=AgentEventType.PERMISSION_POLICY_UPDATED,
                    payload={
                        "permission_policy_version": updated.permission_policy_version,
                        "permission_mode": updated.permission_mode,
                        "pending_strategy": pending_strategy,
                    },
                    visibility="audit",
                    commit=False,
                )

            if pending_strategy == "approve_pending_tools":
                active_actions = await self.action_repo.list_for_active_batches(
                    str(updated.id)
                )
                for action in active_actions:
                    if action.status != AgentActionStatus.WAITING_DECISION:
                        reconciliation["already_resolved_count"] += 1
                        continue
                    if action.name in {"ask_user", "exit_plan_mode"}:
                        reconciliation["excluded_count"] += 1
                        continue
                    decision_payload = {
                        "decision": "approve",
                        "note": "Approved by permission policy update",
                        "source": "user_pending_strategy",
                        "evaluated_policy_version": action.evaluated_policy_version,
                        "modified_input": None,
                        "answer": None,
                    }
                    decided = await self.action_repo.decide_waiting(
                        str(action.id),
                        status=AgentActionStatus.REQUESTED,
                        input=action.input or {},
                        permission_decision=decision_payload,
                    )
                    if decided is None:
                        reconciliation["already_resolved_count"] += 1
                        continue
                    reconciliation["affected_count"] += 1
                    await self.turn_repo.queue_waiting_for_resume(
                        str(decided.turn_id),
                        resume_batch_token=(
                            str(decided.tool_batch_id)
                            if decided.tool_batch_id
                            else None
                        ),
                    )
                    await self.ledger.append(
                        session_id=str(decided.session_id),
                        turn_id=str(decided.turn_id),
                        type=AgentEventType.ACTION_DECISION_RECORDED,
                        payload={
                            "action_id": str(decided.id),
                            "decision": "approve",
                            "source": "user_pending_strategy",
                            "permission_policy_version": updated.permission_policy_version,
                        },
                        commit=False,
                    )
                    wakeups.append(
                        (str(decided.id), str(decided.turn_id), str(decided.session_id))
                    )
                await self.ledger.append(
                    session_id=str(updated.id),
                    turn_id=None,
                    type=AgentEventType.PERMISSION_PENDING_RECONCILED,
                    payload={
                        "pending_strategy": pending_strategy,
                        "permission_policy_version": updated.permission_policy_version,
                        **reconciliation,
                    },
                    visibility="audit",
                    commit=False,
                )

            await self.db.commit()
        except ConflictError:
            raise
        except Exception:
            await self.db.rollback()
            raise

        setattr(updated, "pending_strategy", pending_strategy)
        setattr(updated, "pending_reconciliation", reconciliation)
        for action_id, turn_id, updated_session_id in wakeups:
            enqueue_turn_resume(action_id, turn_id, updated_session_id)
        return updated

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
        execution_scope: dict | None = None,
        metadata: dict | None = None,
    ):
        session = await self.require_session(
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        session_updates: dict[str, object] = {}
        increment_policy_version = False
        if execution_target is not None:
            previous_target = execution_target_from_session(session)
            next_metadata = session_metadata_with_execution_target(
                getattr(session, "session_metadata", None),
                execution_target,
            )
            session_updates["session_metadata"] = next_metadata
            increment_policy_version = previous_target != normalize_execution_target(
                None,
                metadata=next_metadata,
            )
        if execution_scope is not None:
            previous_target = execution_target_from_session(session)
            previous_scope = session_execution_scope_from_metadata(
                getattr(session, "session_metadata", None)
            )
            normalized_scope = normalize_execution_scope(execution_scope)
            base_metadata = session_updates.get(
                "session_metadata", getattr(session, "session_metadata", None)
            )
            if execution_target is None:
                base_metadata = session_metadata_without_execution_target(
                    base_metadata,
                    clear_remote_alias=normalized_scope is not None
                    and normalized_scope.get("mode") == "auto",
                )
            next_metadata = session_metadata_with_execution_scope(
                base_metadata,
                execution_scope,
            )
            session_updates["session_metadata"] = next_metadata
            increment_policy_version = (
                increment_policy_version
                or previous_scope != normalized_scope
                or previous_target
                != normalize_execution_target(None, metadata=next_metadata)
            )
        normalized_active_skill_names = _validated_active_skill_names(
            active_skill_names
        )
        turn_metadata = _metadata_with_active_skill_names(
            metadata,
            normalized_active_skill_names,
        )
        if execution_target is not None:
            turn_metadata = session_metadata_with_execution_target(
                turn_metadata,
                execution_target,
            )
        if execution_scope is not None:
            turn_metadata = session_metadata_with_execution_scope(
                turn_metadata,
                execution_scope,
            )
        transcript_parts = _transcript_parts_for_turn(
            input_text=input_text,
            input_parts=input_parts,
        )
        if not session.title and not await self.turn_repo.list_for_session(
            str(session.id)
        ):
            session_updates["title"] = _generated_session_title(input_text)
        normalized_model_selection = normalize_model_selection(model_selection)
        turn_id = str(uuid4())
        turn = await self.turn_repo.create_with_session_claim(
            session_id=str(session.id),
            turn_id=turn_id,
            session_updates=session_updates,
            increment_policy_version=increment_policy_version,
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
        execution_scope: dict | None = None,
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
            execution_scope=execution_scope,
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
        cancelled_in_runner = cancel_turn_run(str(turn.id))
        return await self._finalize_cancelled_turn(
            turn,
            termination_reason="cancelled",
            event_type=AgentEventType.TURN_CANCELLED,
            event_payload={"task_cancelled": cancelled_in_runner},
        )

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
        cancelled_in_runner = cancel_turn_run(str(turn.id))
        return await self._finalize_cancelled_turn(
            turn,
            termination_reason="interrupted",
            event_type=AgentEventType.TURN_INTERRUPTED,
            event_payload={
                "termination_reason": "interrupted",
                "task_cancelled": cancelled_in_runner,
            },
            interrupted_at=datetime.now(timezone.utc),
        )

    async def _finalize_cancelled_turn(
        self,
        turn,
        *,
        termination_reason: str,
        event_type: str,
        event_payload: dict,
        interrupted_at: datetime | None = None,
    ):
        turn_id = str(turn.id)
        session_id = str(turn.session_id)
        claimed = await self.turn_repo.claim_cancelled(
            turn_id,
            termination_reason=termination_reason,
            interrupted_at=interrupted_at,
        )
        if not claimed:
            await self.db.rollback()
            return await self.turn_repo.get_fresh(turn_id)

        messages = await self.transcript.list_messages(session_id)
        existing_action_results = {
            str((message.message_metadata or {}).get("action_id"))
            for message in messages
            if message.role == "tool"
            and (message.message_metadata or {}).get("action_id")
        }
        now = datetime.now(timezone.utc)
        processed_action_ids: set[str] = set()

        async def append_cancelled_action_result(
            action, *, batch_id: str | None
        ) -> None:
            if str(action.id) in existing_action_results:
                return
            await self.transcript.append_text(
                session_id=session_id,
                turn_id=turn_id,
                role="tool",
                text=json.dumps(
                    {
                        "tool": action.name,
                        "status": action.status,
                        "result": action.result,
                        "error": action.error,
                    },
                    separators=(",", ":"),
                    default=str,
                ),
                metadata={
                    "tool_call_id": action.tool_call_id,
                    "tool": action.name,
                    "action_id": str(action.id),
                    "tool_batch_id": batch_id,
                },
                commit=False,
            )

        batches = await self.tool_batch_repo.list_nonterminal_for_turn(turn_id)
        for batch in batches:
            await self.tool_batch_repo.cancel_nonterminal_pending(str(batch.id))
            for action in await self.action_repo.list_for_batch(str(batch.id)):
                processed_action_ids.add(str(action.id))
                if action.status in {
                    AgentActionStatus.WAITING_DECISION,
                    AgentActionStatus.REQUESTED,
                    AgentActionStatus.RUNNING,
                }:
                    action = await self.action_repo.update_all_pending(
                        action,
                        status=AgentActionStatus.CANCELLED,
                        requires_resume=False,
                        error={
                            "type": "CancelledError",
                            "message": f"Tool action cancelled because the turn was {termination_reason}.",
                        },
                        completed_at=now,
                    )
                await append_cancelled_action_result(action, batch_id=str(batch.id))
        for action in await self.action_repo.list_open_for_turn(turn_id):
            if str(action.id) in processed_action_ids:
                continue
            action = await self.action_repo.update_all_pending(
                action,
                status=AgentActionStatus.CANCELLED,
                requires_resume=False,
                error={
                    "type": "CancelledError",
                    "message": f"Tool action cancelled because the turn was {termination_reason}.",
                },
                completed_at=now,
            )
            await append_cancelled_action_result(
                action,
                batch_id=str(action.tool_batch_id) if action.tool_batch_id else None,
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={
                    "action_id": str(action.id),
                    "tool": action.name,
                    "reason": termination_reason,
                },
                commit=False,
            )
        await self.ledger.append(
            session_id=session_id,
            turn_id=turn_id,
            type=event_type,
            payload=event_payload,
            commit=False,
        )
        await self.db.commit()
        updated = await self.turn_repo.get_fresh(turn_id)
        await self._release_active_if_terminal(updated)
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
        action = await self.action_repo.get_fresh(action_id)
        if action is None:
            raise NotFoundError(f"Agent action not found: {action_id}")
        await self.require_turn(
            turn_id=str(action.turn_id),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        next_input = action.input
        if decision == "modify":
            if modified_input is None:
                raise BadRequestError(
                    "modified_input is required when decision is modify"
                )
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
        decision_payload = {
            "decision": decision,
            "note": note,
            "source": "user",
            "evaluated_policy_version": action.evaluated_policy_version,
            "modified_input": modified_input,
            "answer": answer,
        }
        updated = await self.action_repo.decide_waiting(
            action_id,
            status=status,
            input=next_input,
            permission_decision=decision_payload,
        )
        if updated is None:
            current = await self.action_repo.get_fresh(action_id)
            if current is not None and _same_action_decision(
                current.permission_decision,
                decision_payload,
            ):
                return current
            current_status = current.status if current is not None else "missing"
            raise ConflictError(
                "Agent action already has a different decision "
                f"or terminal state: {current_status}"
            )

        try:
            # Plan approval and its tool decision are one transaction. A
            # duplicate request cannot increment the policy version twice.
            if decision == "approve" and updated.name == "exit_plan_mode":
                await self._activate_execution_toolset(
                    str(updated.session_id), commit=False
                )
            await self.turn_repo.queue_waiting_for_resume(
                str(updated.turn_id),
                resume_batch_token=(
                    str(updated.tool_batch_id) if updated.tool_batch_id else None
                ),
            )
            await self.ledger.append(
                session_id=str(updated.session_id),
                turn_id=str(updated.turn_id),
                type=AgentEventType.ACTION_DECISION_RECORDED,
                payload={
                    "action_id": str(updated.id),
                    "decision": decision,
                    "note": note,
                    **({"answer": answer} if decision == "answer" else {}),
                },
                commit=False,
            )
            await self.db.commit()
        except Exception:
            await self.db.rollback()
            raise
        if updated.kind == "tool":
            enqueue_turn_resume(
                str(updated.id), str(updated.turn_id), str(updated.session_id)
            )
        return updated

    async def _activate_execution_toolset(
        self, session_id: str, *, commit: bool = True
    ) -> None:
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
            commit=commit,
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
        try:
            turn = await self.require_turn(
                turn_id=str(action.turn_id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            raise NotFoundError("Agent action not found") from exc
        if action.kind != "tool":
            raise ConflictError("Only tool actions can be resumed")
        if action.status != AgentActionStatus.REQUESTED or not action.requires_resume:
            raise ConflictError("Tool action is not awaiting resume")
        await self.turn_repo.queue_waiting_for_resume(
            str(turn.id),
            resume_batch_token=(
                str(action.tool_batch_id) if action.tool_batch_id else None
            ),
        )
        await self.db.commit()
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
            raise NotFoundError("Agent action not found")
        try:
            await self.require_turn(
                turn_id=str(action.turn_id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
        except (NotFoundError, PermissionDeniedError) as exc:
            raise NotFoundError("Agent action not found") from exc
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
        turn = await self.turn_repo.get_fresh(turn_id)
        if turn is None:
            return "skipped"

        async def update_recovery_turn(**values):
            updated, owned = await self.turn_repo.update_owned(
                turn_id,
                expected_owner_token=owner_token,
                **values,
            )
            return updated if owned else None

        if turn.status in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            await self._release_active_if_terminal(turn)
            return "skipped"

        now = datetime.now(timezone.utc)
        owner_token = new_turn_owner_token()
        turn, claimed = await self.turn_repo.claim_recovery(
            turn_id,
            owner_token=owner_token,
            claimed_at=now,
            lease_until=now + _turn_lease_duration(),
        )
        if turn is None or not claimed:
            return "skipped"

        open_actions = await self.action_repo.list_open_for_turn(turn_id)
        latest_action = open_actions[0] if open_actions else None

        batches = await self.tool_batch_repo.list_nonterminal_for_turn(turn_id)
        if len(batches) > 1 and any(batch.batch_ordinal is None for batch in batches):
            turn = await update_recovery_turn(
                status=AgentTurnStatus.FAILED,
                termination_reason="model_failed",
                error_code="recovery_ambiguous_tool_batches",
                error_message="Legacy tool batches cannot be ordered safely for recovery.",
                completed_at=now,
                claimed_at=None,
                lease_until=None,
                owner_token=None,
                resume_batch_token=None,
            )
            if turn is None:
                return "skipped"
            await self._release_active_if_terminal(turn)
            return "failed"
        latest_batch = batches[0] if batches else None
        if latest_batch is not None:
            batch_actions = await self.action_repo.list_for_batch(str(latest_batch.id))
            batch_state = await self.tool_batch_repo.continuation_state(
                str(latest_batch.id)
            )
            if batch_state == "evaluating":
                recovered_calls = await self._recoverable_tool_calls(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    expected_count=latest_batch.tool_call_count,
                )
                if recovered_calls is not None:
                    await ToolCallBatchCoordinator(self.db).repair_preparation_failure(
                        batch_id=str(latest_batch.id),
                        session_id=str(turn.session_id),
                        turn_id=str(turn.id),
                        tool_calls=recovered_calls,
                        error_message="Agent process stopped while preparing the tool batch.",
                    )
                    batch_state = await self.tool_batch_repo.continuation_state(
                        str(latest_batch.id)
                    )
                    batch_actions = await self.action_repo.list_for_batch(
                        str(latest_batch.id)
                    )
            batch_statuses = {action.status for action in batch_actions}
            if AgentActionStatus.RUNNING in batch_statuses:
                await self._cancel_open_actions(turn_id, cancelled_at=now)
                turn = await update_recovery_turn(
                    status=AgentTurnStatus.FAILED,
                    termination_reason="model_failed",
                    error_code="recovery_inflight_action",
                    error_message=(
                        "Agent process stopped while a tool action in the batch was running."
                    ),
                    completed_at=now,
                    claimed_at=None,
                    lease_until=None,
                    owner_token=None,
                    resume_batch_token=None,
                    loop_state={
                        "termination_reason": "model_failed",
                        "recovered": True,
                    },
                )
                if turn is None:
                    return "skipped"
                await self._release_active_if_terminal(turn)
                await self.ledger.append(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    type=AgentEventType.TURN_RECOVERY_FAILED,
                    payload={
                        "error_code": "recovery_inflight_action",
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                return "failed"
            if AgentActionStatus.WAITING_DECISION in batch_statuses:
                turn = await update_recovery_turn(
                    status=AgentTurnStatus.WAITING_APPROVAL,
                    claimed_at=None,
                    lease_until=None,
                    owner_token=None,
                    resume_batch_token=str(latest_batch.id),
                    completed_at=None,
                    loop_state={
                        "state": "waiting_approval",
                        "recovered": True,
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                if turn is None:
                    return "skipped"
                return "waiting"
            if AgentActionStatus.REQUESTED in batch_statuses:
                requested_action = next(
                    action
                    for action in batch_actions
                    if action.status == AgentActionStatus.REQUESTED
                )
                turn = await update_recovery_turn(
                    status=AgentTurnStatus.WAITING_APPROVAL,
                    completed_at=None,
                    error_code=None,
                    error_message=None,
                    claimed_at=None,
                    lease_until=None,
                    owner_token=None,
                    resume_batch_token=str(latest_batch.id),
                    loop_state={
                        "state": "waiting_approval",
                        "recovered": True,
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                if turn is None:
                    return "skipped"
                await self.ledger.append(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    type=AgentEventType.TURN_RECOVERY_ENQUEUED,
                    payload={
                        "mode": "batch_resume",
                        "action_id": str(requested_action.id),
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                enqueue_turn_resume(
                    str(requested_action.id), str(turn.id), str(turn.session_id)
                )
                return "enqueued"
            if batch_state == "ready" and batch_actions:
                if latest_batch.status == "continuing":
                    latest_batch = await self.tool_batch_repo.update_all(
                        latest_batch,
                        status="ready",
                        continuation_claimed_at=None,
                    )
                turn = await update_recovery_turn(
                    status=AgentTurnStatus.WAITING_APPROVAL,
                    completed_at=None,
                    error_code=None,
                    error_message=None,
                    claimed_at=None,
                    lease_until=None,
                    owner_token=None,
                    resume_batch_token=str(latest_batch.id),
                    loop_state={
                        "state": "waiting_approval",
                        "recovered": True,
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                if turn is None:
                    return "skipped"
                resume_action = batch_actions[-1]
                await self.ledger.append(
                    session_id=str(turn.session_id),
                    turn_id=str(turn.id),
                    type=AgentEventType.TURN_RECOVERY_ENQUEUED,
                    payload={
                        "mode": "batch_resume",
                        "action_id": str(resume_action.id),
                        "tool_batch_id": str(latest_batch.id),
                    },
                )
                enqueue_turn_resume(
                    str(resume_action.id), str(turn.id), str(turn.session_id)
                )
                return "enqueued"

        if (
            latest_action is not None
            and latest_action.status == AgentActionStatus.WAITING_DECISION
        ):
            turn = await update_recovery_turn(
                status=AgentTurnStatus.WAITING_APPROVAL,
                claimed_at=None,
                lease_until=None,
                owner_token=None,
                resume_batch_token=turn.resume_batch_token,
                completed_at=None,
                loop_state={"state": "waiting_approval", "recovered": True},
            )
            if turn is None:
                return "skipped"
            return "waiting"

        if (
            latest_action is not None
            and latest_action.status == AgentActionStatus.REQUESTED
        ):
            turn = await update_recovery_turn(
                status=AgentTurnStatus.WAITING_APPROVAL,
                completed_at=None,
                error_code=None,
                error_message=None,
                claimed_at=None,
                lease_until=None,
                owner_token=None,
                resume_batch_token=(turn.resume_batch_token or new_turn_owner_token()),
                loop_state={
                    "state": "waiting_approval",
                    "recovered": True,
                    "resume_action_id": str(latest_action.id),
                },
            )
            if turn is None:
                return "skipped"
            await self._release_active_if_terminal(turn)
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

        if (
            latest_action is not None
            and latest_action.status == AgentActionStatus.RUNNING
        ):
            await self._cancel_open_actions(turn_id, cancelled_at=now)
            turn = await update_recovery_turn(
                status=AgentTurnStatus.FAILED,
                termination_reason="model_failed",
                error_code="recovery_inflight_action",
                error_message="Agent process stopped while a tool action was running.",
                completed_at=now,
                claimed_at=None,
                lease_until=None,
                owner_token=None,
                resume_batch_token=None,
                loop_state={"termination_reason": "model_failed", "recovered": True},
            )
            if turn is None:
                return "skipped"
            await self.ledger.append(
                session_id=str(turn.session_id),
                turn_id=str(turn.id),
                type=AgentEventType.TURN_RECOVERY_FAILED,
                payload={"error_code": "recovery_inflight_action"},
            )
            return "failed"

        turn = await update_recovery_turn(
            status=AgentTurnStatus.QUEUED,
            termination_reason=None,
            completed_at=None,
            error_code=None,
            error_message=None,
            claimed_at=None,
            lease_until=None,
            owner_token=None,
            resume_batch_token=None,
            loop_state={"state": "queued", "recovered": True},
        )
        if turn is None:
            return "skipped"
        await self.ledger.append(
            session_id=str(turn.session_id),
            turn_id=str(turn.id),
            type=AgentEventType.TURN_RECOVERY_ENQUEUED,
            payload={"mode": "run"},
        )
        enqueue_turn_run(str(turn.id), str(turn.session_id))
        return "enqueued"

    async def _recoverable_tool_calls(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_count: int,
    ) -> list[dict] | None:
        messages = await self.transcript.list_messages(session_id)
        for message in reversed(messages):
            if str(message.turn_id) != turn_id or message.role != "assistant":
                continue
            for part in message.content_parts or []:
                calls = (
                    part.get("tool_calls") if part.get("type") == "tool_calls" else None
                )
                if not isinstance(calls, list) or len(calls) != expected_count:
                    continue
                recovered: list[dict] = []
                for call in calls:
                    function = call.get("function") or {}
                    raw_arguments = function.get("arguments") or "{}"
                    try:
                        arguments = json.loads(raw_arguments)
                    except (TypeError, ValueError):
                        arguments = {"_raw_arguments": str(raw_arguments)}
                    recovered.append(
                        {
                            "id": call.get("id"),
                            "name": function.get("name") or "unknown",
                            "arguments": arguments,
                        }
                    )
                return recovered
        return None

    async def _cancel_open_actions(
        self, turn_id: str, *, cancelled_at: datetime
    ) -> None:
        for action in await self.action_repo.list_open_for_turn(turn_id):
            await self.action_repo.update_all(
                action,
                status=AgentActionStatus.CANCELLED,
                error={
                    "type": "CancelledError",
                    "message": "Action cancelled with its parent turn.",
                },
                completed_at=cancelled_at,
            )
            await self.ledger.append(
                session_id=str(action.session_id),
                turn_id=str(action.turn_id),
                type=AgentEventType.ACTION_CANCELLED,
                payload={"action_id": str(action.id), "tool": action.name},
            )

    async def _release_active_if_terminal(self, turn) -> None:
        if turn is None or turn.status not in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return
        await self.session_repo.release_active_turn(str(turn.session_id), str(turn.id))

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
    remote_boundary_fingerprint: tuple[Any, ...] | None = None,
) -> tuple[Any, ...]:
    metadata = (
        session.session_metadata if session_metadata is _UNSET else session_metadata
    )
    return (
        str(session.role_profile if role_profile is _UNSET else role_profile),
        str(session.permission_mode if permission_mode is _UNSET else permission_mode),
        str(session.automation_mode if automation_mode is _UNSET else automation_mode),
        _normalized_toolset(
            session.toolset_policy if toolset_policy is _UNSET else toolset_policy
        ),
        tuple(sorted(normalize_execution_target(None, metadata=metadata).items())),
        _normalized_execution_scope(metadata),
        remote_boundary_fingerprint,
    )


def _normalized_execution_scope(metadata: Any) -> tuple[Any, ...] | None:
    scope = session_execution_scope_from_metadata(
        metadata if isinstance(metadata, dict) else None
    )
    if not scope:
        return None
    if scope.get("mode") == "auto":
        return ("auto",)
    targets = scope.get("selected_targets")
    if not isinstance(targets, list):
        return (str(scope.get("mode") or ""),)
    normalized_targets = tuple(
        sorted(
            (
                str(target.get("type") or ""),
                str(target.get("connection_id") or ""),
            )
            for target in targets
            if isinstance(target, dict)
        )
    )
    return (str(scope.get("mode") or ""), normalized_targets)


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


async def _remote_boundary_fingerprint(
    db: AsyncSession,
    *,
    session,
    session_metadata: dict | None,
) -> tuple[Any, ...] | None:
    execution_target = normalize_execution_target(None, metadata=session_metadata)
    if execution_target.get("type") != "remote_ssh":
        return None
    boundary = await RemoteBoundaryResolver(db).resolve(
        agent_session=session,
        connection_id=execution_target.get("connection_id"),
        session_metadata=session_metadata,
    )
    return boundary.policy_fingerprint()


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


def _transcript_parts_for_turn(
    *, input_text: str, input_parts: list[dict] | None
) -> list[dict]:
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
        raise PermissionDeniedError(
            f"File cannot be attached to agent context: {target}"
        )

    label = str(part.get("label") or target.name)
    if part.get("includeContent") is False:
        return (
            f"Attached file reference: {label}\nPath: {target}\nContent: not included."
        )

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

    lines = [
        f"Workflow context: {_workflow_ref_label(scope=scope, project_id=project_id)}"
    ]
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
            "workflow_ref input part has unsupported fields: " + ", ".join(unsupported)
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


def _same_action_decision(current: dict | None, requested: dict) -> bool:
    if not isinstance(current, dict):
        return False
    return all(
        current.get(key) == requested.get(key)
        for key in ("decision", "note", "modified_input", "answer")
    )


def _turn_lease_duration() -> timedelta:
    seconds = max(int(getattr(settings, "agent_turn_lease_seconds", 300) or 300), 1)
    return timedelta(seconds=seconds)
