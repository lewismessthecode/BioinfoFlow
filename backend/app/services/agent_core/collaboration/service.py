from __future__ import annotations

import asyncio
import json
import re
import shutil

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError, OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_core import (
    AgentAttachment,
    AgentMessageStatus,
    AgentSession,
    AgentTurnStatus,
)
from app.path_layout import agent_attachment_root
from app.repositories.agent_core_repo import (
    AgentAttachmentRepository,
    AgentCollaborationCapacityError,
    AgentSessionRepository,
    AgentTurnRepository,
)
from app.services.agent_core.collaboration.context_fork import fork_agent_context
from app.services.agent_core.collaboration.contracts import (
    AgentInterruptResult,
    AgentListItem,
    AgentMessageResult,
    AgentModelChoice,
    AgentWaitResult,
    SpawnAgentResult,
)
from app.services.agent_core.collaboration.model_preflight import AgentModelPreflight
from app.services.agent_core.events import AgentEventType
from app.services.agent_core.ledger import AgentEventLedger
from app.services.agent_core.ownership import TurnOwnershipLostError
from app.services.agent_core.runner import enqueue_turn_run
from app.services.agent_core.service import AgentCoreService
from app.services.agent_core.transcript import AgentTranscriptStore
from app.services.agent_core.transcript.messages import parts_to_text, text_part
from app.services.authorization_service import AuthorizationService
from app.utils.exceptions import BadRequestError, ConflictError, PermissionDeniedError


_AGENT_NAME = re.compile(r"^[a-z0-9_]{1,80}$")
_COLLABORATION_WAITERS: dict[str, set[asyncio.Future[None]]] = {}


def _collaboration_waiter_count() -> int:
    return len(
        {
            future
            for waiters in _COLLABORATION_WAITERS.values()
            for future in waiters
        }
    )


def notify_collaboration_waiters(*session_ids: str) -> None:
    futures = {
        future
        for session_id in session_ids
        for future in _COLLABORATION_WAITERS.get(session_id, set())
    }
    for future in futures:
        if not future.done():
            future.set_result(None)


async def _wait_for_collaboration_notification(
    session_ids: set[str],
    timeout_seconds: float,
) -> None:
    loop = asyncio.get_running_loop()
    future: asyncio.Future[None] = loop.create_future()
    for session_id in session_ids:
        _COLLABORATION_WAITERS.setdefault(session_id, set()).add(future)
    try:
        await asyncio.wait_for(asyncio.shield(future), timeout=timeout_seconds)
    except TimeoutError:
        pass
    finally:
        for session_id in session_ids:
            waiters = _COLLABORATION_WAITERS.get(session_id)
            if waiters is None:
                continue
            waiters.discard(future)
            if not waiters:
                _COLLABORATION_WAITERS.pop(session_id, None)
        if not future.done():
            future.cancel()


class AgentCollaborationService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.sessions = AgentSessionRepository(session)
        self.turns = AgentTurnRepository(session)
        self.attachments = AgentAttachmentRepository(session)
        self.transcript = AgentTranscriptStore(session)
        self.ledger = AgentEventLedger(session)
        self.core = AgentCoreService(session)
        self.model_preflight = AgentModelPreflight(session)

    async def spawn_agent(
        self,
        *,
        parent_session_id: str,
        parent_turn_id: str,
        task_name: str,
        message: str,
        fork_turns: str = "all",
        model: str | None = None,
        reasoning_effort: str | None = None,
    ) -> SpawnAgentResult:
        task_name = str(task_name or "").strip()
        message = str(message or "").strip()
        if not _AGENT_NAME.fullmatch(task_name):
            raise BadRequestError("invalid_agent_name")
        if not message:
            raise BadRequestError("invalid_agent_message")

        parent = await self.sessions.get(parent_session_id)
        parent_turn = await self.turns.get(parent_turn_id)
        if parent is None or parent_turn is None:
            raise BadRequestError("parent_agent_not_found")
        if str(parent_turn.session_id) != str(parent.id):
            raise BadRequestError("parent_turn_mismatch")
        if parent.parent_session_id is not None or parent.root_session_id is not None:
            raise PermissionDeniedError("root_agent_required")
        if (
            str(parent.workspace_id) != str(parent_turn.workspace_id)
            or parent.user_id != parent_turn.user_id
        ):
            raise PermissionDeniedError("parent_agent_scope_mismatch")

        parent_messages = await self.transcript.list_messages(str(parent.id))
        forked_messages = fork_agent_context(parent_messages, fork_turns=fork_turns)
        parent_snapshot = dict(parent_turn.model_profile_snapshot or {})
        parent_model_id, parent_model_name = _parent_model(parent_snapshot)
        parent_effort = _parent_reasoning_effort(parent_snapshot)
        parent_data = _parent_session_data(parent)
        workspace_id = str(parent.workspace_id)
        user_id = parent.user_id
        root_session_id = str(parent.id)
        role = await AuthorizationService(self.db).resolve_workspace_role(
            workspace_id=workspace_id,
            user_id=user_id,
            fallback_role="owner" if settings.auth_is_personal else None,
        )
        choice = await self.model_preflight.resolve(
            requested_model=model,
            parent_model=parent_model_name,
            parent_model_id=parent_model_id,
            parent_reasoning_effort=parent_effort,
            requested_reasoning_effort=reasoning_effort,
            parent_supports_reasoning=_parent_supports_reasoning(parent_snapshot),
            role=role,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        await self.db.rollback()

        copied_roots: list[Path] = []
        try:
            duplicate = await self.sessions.get_agent_target(
                root_session_id,
                task_name,
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if duplicate is not None:
                raise ConflictError("agent_name_reserved")

            child = await self.core.create_session(
                project_id=parent_data["project_id"],
                workspace_id=workspace_id,
                user_id=user_id,
                title=f"Agent: {task_name}",
                role_profile="subagent",
                permission_mode=parent_data["permission_mode"],
                automation_mode=parent_data["automation_mode"],
                default_model_profile_id=None,
                model_selection={"model_id": choice.effective_model_id},
                metadata=_child_metadata(parent_data["metadata"], choice),
                lineage={
                    "parent_session_id": root_session_id,
                    "parent_turn_id": parent_turn_id,
                    "root_session_id": root_session_id,
                    "agent_name": task_name,
                },
                toolset_policy=parent_data["toolset_policy"],
                prompt_snapshot=parent_data["prompt_snapshot"],
                commit=False,
            )
            child.parent_session_id = root_session_id
            child.root_session_id = root_session_id
            child.agent_name = task_name
            child.spawned_by_turn_id = parent_turn_id
            await self.db.flush()
            await self.sessions.reserve_child_slot(child)

            forked_messages = await self._reown_forked_attachments(
                forked_messages,
                child=child,
                parent_session_id=root_session_id,
                workspace_id=workspace_id,
                user_id=user_id,
                copied_roots=copied_roots,
            )
            for ordering_index, item in enumerate(forked_messages, start=1):
                await self.transcript.append_parts(
                    session_id=str(child.id),
                    turn_id=None,
                    role=item["role"],
                    parts=item["content_parts"],
                    metadata=item.get("message_metadata"),
                    status=AgentMessageStatus.COMMITTED,
                    ordering_index=ordering_index,
                    commit=False,
                )

            child_turn = await self.core.create_turn_record(
                session_id=str(child.id),
                workspace_id=workspace_id,
                user_id=user_id,
                input_text=message,
                model_selection={"model_id": choice.effective_model_id},
                metadata={
                    "collaboration": {
                        "parent_session_id": root_session_id,
                        "parent_turn_id": parent_turn_id,
                        "agent_name": task_name,
                        "requested_model": choice.requested_model,
                        "effective_model": choice.effective_model,
                        "model_fallback": choice.fallback,
                        "fallback_reason": choice.fallback_reason,
                        "reasoning_effort": choice.reasoning_effort,
                    }
                },
                commit=False,
            )
            await self.db.commit()
        except AgentCollaborationCapacityError as exc:
            await self.db.rollback()
            _remove_copied_roots(copied_roots)
            raise ConflictError("agent_limit_reached") from exc
        except IntegrityError as exc:
            await self.db.rollback()
            _remove_copied_roots(copied_roots)
            raise ConflictError("agent_name_reserved") from exc
        except BaseException:
            await self.db.rollback()
            _remove_copied_roots(copied_roots)
            raise

        child_id = str(child.id)
        child_turn_id = str(child_turn.id)
        task_path = f"/root/{task_name}"
        lifecycle_payload = {
            "child_session_id": child_id,
            "child_turn_id": child_turn_id,
            "task_name": task_path,
            "requested_model": choice.requested_model,
            "effective_model": choice.effective_model,
            "model_fallback": choice.fallback,
            "fallback_reason": choice.fallback_reason,
        }
        await self._publish_root_activity(
            root_id=root_session_id,
            event_type=AgentEventType.AGENT_SPAWNED,
            payload=lifecycle_payload,
        )
        if choice.fallback:
            await self._publish_root_activity(
                root_id=root_session_id,
                event_type=AgentEventType.AGENT_MODEL_FALLBACK,
                payload=lifecycle_payload,
            )
        try:
            enqueue_turn_run(child_turn_id, child_id)
        except Exception:
            # The committed queued turn is intentionally left for startup recovery.
            pass
        return SpawnAgentResult(
            child_session_id=child_id,
            child_turn_id=child_turn_id,
            task_name=task_path,
            status="pending_init",
            requested_model=choice.requested_model,
            effective_model=choice.effective_model,
            effective_model_id=choice.effective_model_id,
            reasoning_effort=choice.reasoning_effort,
            model_fallback=choice.fallback,
            fallback_reason=choice.fallback_reason,
        )

    async def send_message(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        target: str,
        message: str,
    ) -> AgentMessageResult:
        message = str(message or "").strip()
        if not message:
            raise BadRequestError("invalid_agent_message")
        caller, root_id, target_session = await self._resolve_target(
            caller_session_id=caller_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            target=target,
        )
        target_id = str(target_session.id)
        target_name = _canonical_name(target_session, root_id)
        activity_session = caller if target_id == root_id else target_session
        activity_session_id = str(activity_session.id)
        activity_task_name = _canonical_name(activity_session, root_id)
        active = await self._active_turn(target_session)
        target_turns = await self.turns.list_for_session(target_id)
        current = active or (target_turns[-1] if target_turns else None)
        active_status = _external_status(current)
        metadata = self._message_metadata(
            kind="inter_agent_message",
            root_id=root_id,
            caller=caller,
            delivery="steer" if active is not None else "queued",
        )
        if active is not None:
            try:
                await self.core.steer_turn(
                    turn_id=str(active.id),
                    workspace_id=workspace_id,
                    user_id=user_id,
                    input_text=message,
                    metadata=metadata,
                )
                await self._publish_root_activity(
                    root_id=root_id,
                    event_type=AgentEventType.AGENT_MESSAGE_RECEIVED,
                    payload={
                        "child_session_id": activity_session_id,
                        "task_name": activity_task_name,
                        "delivery": "steer",
                    },
                )
                return AgentMessageResult(
                    target=target_name,
                    delivery="steer",
                    status=_external_status(active),
                    turn_id=str(active.id),
                )
            except ConflictError:
                await self.db.rollback()
                target_session = await self.sessions.get_fresh(target_id)
                if target_session is None:
                    raise BadRequestError("agent_target_not_found")

        metadata["delivery"] = "queued"
        await self.transcript.append_parts(
            session_id=str(target_session.id),
            turn_id=None,
            role="user",
            parts=[text_part(message)],
            metadata=metadata,
            status=AgentMessageStatus.DRAFT,
            commit=False,
        )
        await self._publish_root_activity(
            root_id=root_id,
            event_type=AgentEventType.AGENT_MESSAGE_RECEIVED,
            payload={
                "child_session_id": activity_session_id,
                "task_name": activity_task_name,
                "delivery": "queued",
            },
        )
        notify_collaboration_waiters(root_id, target_id)
        return AgentMessageResult(
            target=target_name,
            delivery="queued",
            status=active_status,
        )

    async def followup_task(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        target: str,
        message: str,
    ) -> AgentMessageResult:
        for attempt in range(4):
            try:
                return await self._followup_task_once(
                    caller_session_id=caller_session_id,
                    workspace_id=workspace_id,
                    user_id=user_id,
                    target=target,
                    message=message,
                )
            except OperationalError as exc:
                await self.db.rollback()
                if "locked" not in str(exc).lower() or attempt == 3:
                    raise
                await asyncio.sleep(0.02 * (attempt + 1))
        raise RuntimeError("unreachable")

    async def _followup_task_once(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        target: str,
        message: str,
    ) -> AgentMessageResult:
        message = str(message or "").strip()
        if not message:
            raise BadRequestError("invalid_agent_message")
        caller, root_id, child = await self._resolve_target(
            caller_session_id=caller_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            target=target,
        )
        child_id = str(child.id)
        caller_id = str(caller.id)
        if str(child.id) == root_id:
            raise PermissionDeniedError("child_agent_required")

        active = await self._active_turn(child)
        metadata = self._message_metadata(
            kind="agent_followup",
            root_id=root_id,
            caller=caller,
            delivery="steer" if active is not None else "followup",
        )
        if active is not None:
            try:
                await self.core.steer_turn(
                    turn_id=str(active.id),
                    workspace_id=workspace_id,
                    user_id=user_id,
                    input_text=message,
                    metadata=metadata,
                )
                await self._publish_root_activity(
                    root_id=root_id,
                    event_type=AgentEventType.AGENT_FOLLOWUP_RECEIVED,
                    payload={
                        "child_session_id": child_id,
                        "child_turn_id": str(active.id),
                        "task_name": _canonical_name(child, root_id),
                        "delivery": "steer",
                    },
                )
                return AgentMessageResult(
                    target=_canonical_name(child, root_id),
                    delivery="steer",
                    status=_external_status(active),
                    turn_id=str(active.id),
                )
            except ConflictError:
                await self.db.rollback()
                child = await self.sessions.get_fresh(child_id)
                if child is None:
                    raise BadRequestError("agent_target_not_found")
                caller = await self.sessions.get_fresh(caller_id)
                if caller is None:
                    raise PermissionDeniedError("agent_caller_scope_mismatch")

        try:
            return await self._start_followup(
                child=child,
                caller=caller,
                root_id=root_id,
                workspace_id=workspace_id,
                user_id=user_id,
                message=message,
            )
        except ConflictError:
            await self.db.rollback()
            child = await self.sessions.get_fresh(child_id)
            if child is None:
                raise BadRequestError("agent_target_not_found")
            caller = await self.sessions.get_fresh(caller_id)
            if caller is None:
                raise PermissionDeniedError("agent_caller_scope_mismatch")
            active = await self._active_turn(child)
            if active is not None and active.accepts_steer:
                try:
                    await self.core.steer_turn(
                        turn_id=str(active.id),
                        workspace_id=workspace_id,
                        user_id=user_id,
                        input_text=message,
                        metadata=metadata,
                    )
                    await self._publish_root_activity(
                        root_id=root_id,
                        event_type=AgentEventType.AGENT_FOLLOWUP_RECEIVED,
                        payload={
                            "child_session_id": child_id,
                            "child_turn_id": str(active.id),
                            "task_name": _canonical_name(child, root_id),
                            "delivery": "steer",
                        },
                    )
                    return AgentMessageResult(
                        target=_canonical_name(child, root_id),
                        delivery="steer",
                        status=_external_status(active),
                        turn_id=str(active.id),
                    )
                except ConflictError:
                    await self.db.rollback()
            await self.transcript.append_parts(
                session_id=str(child.id),
                turn_id=None,
                role="user",
                parts=[text_part(message)],
                metadata={**metadata, "delivery": "queued"},
                status=AgentMessageStatus.DRAFT,
            )
            await self._publish_root_activity(
                root_id=root_id,
                event_type=AgentEventType.AGENT_FOLLOWUP_RECEIVED,
                payload={
                    "child_session_id": child_id,
                    "child_turn_id": str(active.id) if active is not None else None,
                    "task_name": _canonical_name(child, root_id),
                    "delivery": "queued",
                },
            )
            return AgentMessageResult(
                target=_canonical_name(child, root_id),
                delivery="queued",
                status=_external_status(active),
                turn_id=str(active.id) if active is not None else None,
            )

    async def interrupt_agent(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        target: str,
    ) -> AgentInterruptResult:
        caller, root_id, child = await self._resolve_target(
            caller_session_id=caller_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
            target=target,
        )
        if str(child.id) == root_id:
            raise PermissionDeniedError("child_agent_required")
        if str(child.id) == str(caller.id):
            raise PermissionDeniedError("cannot_interrupt_self")
        target_name = _canonical_name(child, root_id)
        active = await self._active_turn(child)
        turns = await self.turns.list_for_session(str(child.id))
        previous = _external_status(active or (turns[-1] if turns else None))
        if active is not None:
            await self.core.interrupt_turn(
                turn_id=str(active.id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
        return AgentInterruptResult(
            target=target_name,
            status=previous,
        )

    async def wait_agent(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        timeout_ms: int = 30_000,
    ) -> AgentWaitResult:
        if timeout_ms < 0 or timeout_ms > 60_000:
            raise BadRequestError("invalid_wait_timeout")
        caller = await self._require_caller(
            caller_session_id=caller_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        caller_id = str(caller.id)
        root_id = str(caller.root_session_id or caller.id)
        caller_name = _canonical_name(caller, root_id)
        deadline = asyncio.get_running_loop().time() + timeout_ms / 1000
        while True:
            await self.db.rollback()
            caller = await self.sessions.get_fresh(caller_id)
            if caller is None:
                raise PermissionDeniedError("agent_caller_scope_mismatch")
            metadata = dict(caller.session_metadata or {})
            cursors = dict(metadata.get("collaboration_wait_cursors") or {})
            root_cursor = int(cursors.get("root") or 0)
            caller_cursor = int(cursors.get("caller") or 0)
            root_events = await self.ledger.event_repo.list_for_session(
                session_id=root_id,
                after_seq=root_cursor,
                event_types={
                    AgentEventType.AGENT_MESSAGE_RECEIVED,
                    AgentEventType.AGENT_RESULT_RECEIVED,
                    AgentEventType.TURN_STEER_RECEIVED,
                },
            )
            caller_events = []
            if caller_id != root_id:
                caller_events = await self.ledger.event_repo.list_for_session(
                    session_id=caller_id,
                    after_seq=caller_cursor,
                    event_types={AgentEventType.TURN_STEER_RECEIVED},
                )
            events = [*root_events, *caller_events]
            if events:
                if root_events:
                    cursors["root"] = max(event.seq for event in root_events)
                if caller_events:
                    cursors["caller"] = max(event.seq for event in caller_events)
                metadata["collaboration_wait_cursors"] = cursors
                caller.session_metadata = metadata
                await self.db.commit()
                names = {
                    str(event.payload.get("task_name"))
                    for event in root_events
                    if event.payload.get("task_name")
                }
                if caller_events:
                    names.add(caller_name)
                return AgentWaitResult(
                    timed_out=False,
                    updated_agents=sorted(names),
                )
            if asyncio.get_running_loop().time() >= deadline:
                return AgentWaitResult(timed_out=True, updated_agents=[])
            remaining = max(deadline - asyncio.get_running_loop().time(), 0)
            await _wait_for_collaboration_notification(
                {root_id, caller_id},
                min(remaining, 1.0),
            )

    async def publish_child_terminal(self, *, turn_id: str) -> None:
        for attempt in range(4):
            try:
                await self._publish_child_terminal_once(turn_id=turn_id)
                return
            except OperationalError as exc:
                await self.db.rollback()
                if "locked" not in str(exc).lower() or attempt == 3:
                    raise
                await asyncio.sleep(0.02 * (attempt + 1))

    async def publish_child_running(
        self,
        *,
        turn_id: str,
        expected_owner_token: str,
    ) -> bool:
        turn = await self.turns.get_fresh(turn_id)
        if turn is None:
            return False
        child = await self.sessions.get_fresh(str(turn.session_id))
        if child is None or child.root_session_id is None:
            return False
        collaboration = (child.session_metadata or {}).get("collaboration") or {}
        root_id = str(child.root_session_id)
        try:
            await self.ledger.append(
                session_id=root_id,
                turn_id=turn_id,
                type=AgentEventType.AGENT_RUNNING,
                payload={
                    "child_session_id": str(child.id),
                    "child_turn_id": str(turn.id),
                    "task_name": _canonical_name(child, root_id),
                    "requested_model": collaboration.get("requested_model"),
                    "effective_model": collaboration.get("effective_model"),
                    "model_fallback": bool(
                        collaboration.get("model_fallback", False)
                    ),
                    "fallback_reason": collaboration.get("fallback_reason"),
                },
                visibility="internal",
                expected_owner_token=expected_owner_token,
            )
        except TurnOwnershipLostError:
            return False
        notify_collaboration_waiters(root_id)
        return True

    async def _publish_child_terminal_once(self, *, turn_id: str) -> None:
        turn = await self.turns.get_fresh(turn_id)
        if turn is None or turn.status not in {
            AgentTurnStatus.COMPLETED,
            AgentTurnStatus.FAILED,
            AgentTurnStatus.CANCELLED,
        }:
            return
        child = await self.sessions.get_fresh(str(turn.session_id))
        if child is None or child.root_session_id is None:
            return
        child_id = str(child.id)
        root_id = str(child.root_session_id)
        root = await self.sessions.get_fresh(root_id)
        if root is None:
            return
        await self.sessions.lock_policy(root_id)
        messages = await self.transcript.list_messages(root_id)
        if any(
            (message.message_metadata or {}).get("source_turn_id") == turn_id
            and (message.message_metadata or {}).get("collaboration_kind")
            == "agent_result"
            for message in messages
        ):
            await self.sessions.finalize_child_terminal_state(child_id, turn_id)
            if not await self._has_publication_marker(turn_id):
                await self.ledger.append(
                    session_id=child_id,
                    turn_id=turn_id,
                    type=AgentEventType.AGENT_RESULT_PUBLISHED,
                    payload={"root_session_id": root_id},
                    visibility="internal",
                    commit=False,
                )
            await self.db.commit()
            notify_collaboration_waiters(root_id, child_id)
            await self._schedule_pending_followup(child=child, root=root)
            return

        payload = _terminal_payload(child, turn)
        text = json.dumps(
            {"agent_result": payload},
            ensure_ascii=False,
            separators=(",", ":"),
        )
        active_parent = await self._active_turn(root)
        metadata = {
            "kind": "agent_result",
            "collaboration_kind": "agent_result",
            "source_turn_id": turn_id,
            "agent_result": payload,
            "root_session_id": root_id,
            "delivery": "steer" if active_parent is not None else "queued",
            "consumed": False,
        }
        await self.transcript.append_parts(
            session_id=root_id,
            turn_id=None,
            role="user",
            parts=[text_part(text)],
            metadata=metadata,
            status=AgentMessageStatus.DRAFT,
            commit=False,
        )
        await self.sessions.finalize_child_terminal_state(child_id, turn_id)
        await self.ledger.append(
            session_id=root_id,
            turn_id=str(active_parent.id) if active_parent is not None else None,
            type=AgentEventType.AGENT_RESULT_RECEIVED,
            payload=payload,
            visibility="internal",
            commit=False,
        )
        await self.ledger.append(
            session_id=child_id,
            turn_id=turn_id,
            type=AgentEventType.AGENT_RESULT_PUBLISHED,
            payload={"root_session_id": root_id},
            visibility="internal",
            commit=False,
        )
        await self.db.commit()
        notify_collaboration_waiters(root_id, child_id)
        await self._schedule_pending_followup(child=child, root=root)

    async def _has_publication_marker(self, turn_id: str) -> bool:
        events = await self.ledger.event_repo.list_for_turn(
            turn_id=turn_id,
            event_types={AgentEventType.AGENT_RESULT_PUBLISHED},
        )
        return bool(events)

    async def recover_pending_followups(self) -> int:
        child_ids = [
            str(child.id)
            for child in await self.sessions.list_idle_children_with_draft_messages()
        ]
        recovered = 0
        for child_id in child_ids:
            for attempt in range(4):
                try:
                    await self.db.rollback()
                    child = await self.sessions.get_fresh(child_id)
                    if (
                        child is None
                        or child.root_session_id is None
                        or child.active_turn_id is not None
                        or child.collaboration_slot is not None
                    ):
                        break
                    root = await self.sessions.get_fresh(str(child.root_session_id))
                    if root is None:
                        break
                    if await self._schedule_pending_followup(child=child, root=root):
                        recovered += 1
                    break
                except OperationalError as exc:
                    await self.db.rollback()
                    if "locked" not in str(exc).lower() or attempt == 3:
                        raise
                    await asyncio.sleep(0.02 * (attempt + 1))
        return recovered

    async def list_agents(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> list[AgentListItem]:
        caller = await self.sessions.get(caller_session_id)
        if caller is None:
            return []
        root_id = str(caller.root_session_id or caller.id)
        tree = await self.sessions.list_agent_tree(
            root_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        result: list[AgentListItem] = []
        for session in tree:
            turns = await self.turns.list_for_session(str(session.id))
            latest = None
            if session.active_turn_id:
                latest = await self.turns.get_fresh(str(session.active_turn_id))
            if latest is None:
                latest = turns[-1] if turns else None
            collaboration = (session.session_metadata or {}).get("collaboration") or {}
            result.append(
                AgentListItem(
                    agent_id=str(session.id),
                    task_name=(
                        "/root"
                        if str(session.id) == root_id
                        else f"/root/{session.agent_name}"
                    ),
                    status=_external_status(latest),
                    current_turn_id=str(latest.id) if latest is not None else None,
                    requested_model=collaboration.get("requested_model"),
                    effective_model=collaboration.get("effective_model"),
                    model_fallback=bool(collaboration.get("model_fallback", False)),
                    fallback_reason=collaboration.get("fallback_reason"),
                    final_text=latest.final_text if latest is not None else None,
                    error_code=latest.error_code if latest is not None else None,
                    error_message=_safe_agent_error(latest),
                    created_at=session.created_at.isoformat(),
                    updated_at=session.updated_at.isoformat(),
                )
            )
        return result

    async def _require_caller(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> AgentSession:
        caller = await self.sessions.get_fresh(caller_session_id)
        if (
            caller is None
            or str(caller.workspace_id) != str(workspace_id)
            or caller.user_id != user_id
        ):
            raise PermissionDeniedError("agent_caller_scope_mismatch")
        root_id = str(caller.root_session_id or caller.id)
        tree = await self.sessions.list_agent_tree(
            root_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if not any(str(item.id) == str(caller.id) for item in tree):
            raise PermissionDeniedError("agent_caller_scope_mismatch")
        return caller

    async def _resolve_target(
        self,
        *,
        caller_session_id: str,
        workspace_id: str,
        user_id: str,
        target: str,
    ) -> tuple[AgentSession, str, AgentSession]:
        caller = await self._require_caller(
            caller_session_id=caller_session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        root_id = str(caller.root_session_id or caller.id)
        resolved = await self.sessions.get_agent_target(
            root_id,
            str(target or ""),
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if resolved is None:
            raise BadRequestError("agent_target_not_found")
        return caller, root_id, resolved

    async def _active_turn(self, session: AgentSession):
        if session.active_turn_id:
            turn = await self.turns.get_fresh(str(session.active_turn_id))
            if turn is not None and _external_status(turn) in {
                "pending_init",
                "running",
            }:
                return turn
        turns = await self.turns.list_for_session(str(session.id))
        if turns and _external_status(turns[-1]) in {"pending_init", "running"}:
            return turns[-1]
        return None

    def _message_metadata(
        self,
        *,
        kind: str,
        root_id: str,
        caller: AgentSession,
        delivery: str,
    ) -> dict:
        return {
            "kind": kind,
            "collaboration_kind": kind,
            "root_session_id": root_id,
            "sender_session_id": str(caller.id),
            "delivery": delivery,
            "consumed": False,
        }

    async def _publish_root_activity(
        self,
        *,
        root_id: str,
        event_type: str,
        payload: dict,
    ) -> None:
        await self.ledger.append(
            session_id=root_id,
            turn_id=None,
            type=event_type,
            payload=payload,
            visibility="internal",
        )
        notify_collaboration_waiters(root_id)

    async def _start_followup(
        self,
        *,
        child: AgentSession,
        caller: AgentSession,
        root_id: str,
        workspace_id: str,
        user_id: str,
        message: str,
    ) -> AgentMessageResult:
        try:
            await self.sessions.reserve_child_slot(child)
        except AgentCollaborationCapacityError as exc:
            await self.db.rollback()
            raise ConflictError("agent_limit_reached") from exc
        collaboration = (child.session_metadata or {}).get("collaboration") or {}
        model_id = collaboration.get("effective_model_id")
        turn = await self.core.create_turn_record(
            session_id=str(child.id),
            workspace_id=workspace_id,
            user_id=user_id,
            input_text=message,
            model_selection={"model_id": model_id} if model_id else None,
            metadata={
                "collaboration": {
                    "root_session_id": root_id,
                    "parent_session_id": root_id,
                    "agent_name": child.agent_name,
                    "followup_from_session_id": str(caller.id),
                }
            },
            commit=False,
        )
        child_id = str(child.id)
        turn_id = str(turn.id)
        target_name = _canonical_name(child, root_id)
        await self.db.commit()
        notify_collaboration_waiters(root_id, child_id)
        await self._publish_root_activity(
            root_id=root_id,
            event_type=AgentEventType.AGENT_FOLLOWUP_RECEIVED,
            payload={
                "child_session_id": child_id,
                "child_turn_id": turn_id,
                "task_name": target_name,
                "delivery": "followup",
            },
        )
        try:
            enqueue_turn_run(turn_id, child_id)
        except Exception:
            pass
        return AgentMessageResult(
            target=target_name,
            delivery="followup",
            status="pending_init",
            turn_id=turn_id,
        )

    async def _schedule_pending_followup(
        self,
        *,
        child: AgentSession,
        root: AgentSession,
    ) -> bool:
        child_id = str(child.id)
        root_id = str(root.id)
        await self.db.rollback()
        child = await self.sessions.get_fresh(child_id)
        root = await self.sessions.get_fresh(root_id)
        if child is None or root is None:
            return False
        pending = [
            message
            for message in await self.transcript.list_messages(child_id)
            if message.status == AgentMessageStatus.DRAFT
            and (message.message_metadata or {}).get("kind") == "agent_followup"
            and (message.message_metadata or {}).get("delivery") == "queued"
        ]
        if not pending:
            return False
        message = pending[0]
        message.status = AgentMessageStatus.SUPERSEDED
        try:
            await self._start_followup(
                child=child,
                caller=root,
                root_id=root_id,
                workspace_id=str(child.workspace_id),
                user_id=child.user_id,
                message=parts_to_text(message.content_parts),
            )
            return True
        except ConflictError:
            await self.db.rollback()
            return False

    async def _reown_forked_attachments(
        self,
        messages: list[dict],
        *,
        child: AgentSession,
        parent_session_id: str,
        workspace_id: str,
        user_id: str,
        copied_roots: list[Path],
    ) -> list[dict]:
        replacements: dict[str, str] = {}
        result = deepcopy(messages)
        for item in result:
            for part in item["content_parts"]:
                source_id = part.pop("source_attachment_id", None)
                if source_id is None:
                    continue
                replacement = replacements.get(source_id)
                if replacement is None:
                    source = await self.attachments.get_owned(
                        source_id,
                        session_id=parent_session_id,
                        workspace_id=workspace_id,
                        user_id=user_id,
                    )
                    if source is None or source.kind != "image":
                        raise BadRequestError("fork_attachment_not_found")
                    clone_id = str(uuid4())
                    clone_root = agent_attachment_root(str(child.id), clone_id)
                    copied_roots.append(clone_root)
                    _clone_attachment_files(source=source, destination=clone_root)
                    await self.attachments.add(
                        id=clone_id,
                        session_id=str(child.id),
                        workspace_id=workspace_id,
                        user_id=user_id,
                        kind=source.kind,
                        source="agent_fork",
                        filename=source.filename,
                        storage_path=f"{child.id}/{clone_id}",
                        mime_type=source.mime_type,
                        size_bytes=source.size_bytes,
                        file_count=source.file_count,
                        image_width=source.image_width,
                        image_height=source.image_height,
                        status=source.status,
                        attachment_metadata=deepcopy(source.attachment_metadata),
                        error_message=source.error_message,
                    )
                    replacement = clone_id
                    replacements[source_id] = replacement
                part["attachment_id"] = replacement
        return result


def _parent_model(snapshot: dict) -> tuple[str, str]:
    model_id = str(snapshot.get("resolved_model_id") or "").strip()
    selection = snapshot.get("resolved_model_selection") or {}
    model_name = str(selection.get("model") or "").strip()
    if not model_id or not model_name:
        raise BadRequestError("parent_model_unresolved")
    return model_id, model_name


def _parent_reasoning_effort(snapshot: dict) -> str | None:
    strategy = snapshot.get("resolved_runtime_strategy")
    value = strategy.get("reasoning_effort") if isinstance(strategy, dict) else None
    if value in {"low", "medium", "high"}:
        return value
    if isinstance(strategy, dict) and strategy.get("allow_thinking") is True:
        return "medium"
    return None


def _parent_supports_reasoning(snapshot: dict) -> bool | None:
    capabilities = snapshot.get("resolved_model_capabilities")
    if not isinstance(capabilities, dict):
        return None
    value = capabilities.get("supports_reasoning")
    return value if isinstance(value, bool) else None


def _parent_session_data(parent: AgentSession) -> dict:
    return {
        "project_id": str(parent.project_id) if parent.project_id else None,
        "permission_mode": parent.permission_mode,
        "automation_mode": parent.automation_mode,
        "toolset_policy": deepcopy(parent.toolset_policy) or {"name": "execution"},
        "prompt_snapshot": deepcopy(parent.prompt_snapshot),
        "metadata": deepcopy(parent.session_metadata),
    }


def _child_metadata(metadata: dict | None, choice: AgentModelChoice) -> dict:
    result = deepcopy(metadata) if isinstance(metadata, dict) else {}
    result["collaboration"] = {
        "requested_model": choice.requested_model,
        "effective_model": choice.effective_model,
        "effective_model_id": choice.effective_model_id,
        "model_fallback": choice.fallback,
        "fallback_reason": choice.fallback_reason,
        "reasoning_effort": choice.reasoning_effort,
    }
    return result


def _external_status(turn) -> str:
    if turn is None or turn.status == AgentTurnStatus.QUEUED:
        return "pending_init"
    if turn.status in {
        AgentTurnStatus.RUNNING,
        AgentTurnStatus.WAITING_USER,
        AgentTurnStatus.WAITING_APPROVAL,
    }:
        return "running"
    if turn.status == AgentTurnStatus.COMPLETED:
        return "completed"
    if turn.status == AgentTurnStatus.CANCELLED:
        return "interrupted"
    return "errored"


def _safe_agent_error(turn) -> str | None:
    if turn is None or _external_status(turn) != "errored":
        return None
    error_code = str(turn.error_code or "").strip()
    raw = str(turn.error_message or "").lower()
    if error_code == "model_request_failed":
        if "authentication" in raw or "unauthorized" in raw or "401" in raw:
            return "Model provider authentication failed."
        if "rate" in raw or "429" in raw:
            return "Model provider rate limit was reached."
        return "The model request failed."
    stable_messages = {
        "model_selection_missing": "No usable model is configured for this agent.",
        "session_not_found": "The agent session could not be loaded.",
        "execution_claim_lost": "The agent execution lease was replaced.",
        "iteration_limit": "The agent reached its iteration limit.",
    }
    return stable_messages.get(error_code, "Agent failed before completing the task.")


def _canonical_name(session: AgentSession, root_id: str) -> str:
    if str(session.id) == root_id:
        return "/root"
    return f"/root/{session.agent_name}"


def _terminal_payload(child: AgentSession, turn) -> dict:
    status = _external_status(turn)
    snapshot = turn.model_profile_snapshot or {}
    selection = snapshot.get("resolved_model_selection") or {}
    collaboration = (child.session_metadata or {}).get("collaboration") or {}
    effective_model = selection.get("model") or collaboration.get("effective_model")
    return {
        "child_session_id": str(child.id),
        "child_turn_id": str(turn.id),
        "task_name": _canonical_name(child, str(child.root_session_id)),
        "status": status,
        "final_text": str(turn.final_text or "").strip() or None,
        "error_code": turn.error_code,
        "error_message": _safe_terminal_message(turn, status=status),
        "termination_reason": turn.termination_reason,
        "token_usage": turn.token_usage,
        "effective_model": effective_model,
    }


def _safe_terminal_message(turn, *, status: str) -> str:
    error = _safe_agent_error(turn)
    if error:
        return error
    if status == "completed":
        return "Agent completed successfully."
    if status == "interrupted":
        return "Agent was interrupted."
    return "Agent failed before completing the task."


def _clone_attachment_files(*, source: AgentAttachment, destination: Path) -> None:
    source_root = agent_attachment_root(str(source.session_id), str(source.id))
    if not source_root.is_dir():
        raise BadRequestError("fork_attachment_storage_missing")
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source_root, destination)
    except BaseException:
        shutil.rmtree(destination, ignore_errors=True)
        raise


def _remove_copied_roots(paths: list[Path]) -> None:
    for path in paths:
        shutil.rmtree(path, ignore_errors=True)
    for parent in {path.parent for path in paths}:
        try:
            parent.rmdir()
        except OSError:
            pass
