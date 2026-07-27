from __future__ import annotations

import re
import shutil

from copy import deepcopy
from pathlib import Path
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
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
    AgentListItem,
    AgentModelChoice,
    SpawnAgentResult,
)
from app.services.agent_core.collaboration.model_preflight import AgentModelPreflight
from app.services.agent_core.runner import enqueue_turn_run
from app.services.agent_core.service import AgentCoreService
from app.services.agent_core.transcript import AgentTranscriptStore
from app.services.authorization_service import AuthorizationService
from app.utils.exceptions import BadRequestError, ConflictError, PermissionDeniedError


_AGENT_NAME = re.compile(r"^[a-z0-9_]{1,80}$")


class AgentCollaborationService:
    def __init__(self, session: AsyncSession):
        self.db = session
        self.sessions = AgentSessionRepository(session)
        self.turns = AgentTurnRepository(session)
        self.attachments = AgentAttachmentRepository(session)
        self.transcript = AgentTranscriptStore(session)
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

        try:
            enqueue_turn_run(str(child_turn.id), str(child.id))
        except Exception:
            # The committed queued turn is intentionally left for startup recovery.
            pass
        return SpawnAgentResult(
            child_session_id=str(child.id),
            child_turn_id=str(child_turn.id),
            task_name=f"/root/{task_name}",
            status="pending_init",
            requested_model=choice.requested_model,
            effective_model=choice.effective_model,
            effective_model_id=choice.effective_model_id,
            reasoning_effort=choice.reasoning_effort,
            model_fallback=choice.fallback,
            fallback_reason=choice.fallback_reason,
        )

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
