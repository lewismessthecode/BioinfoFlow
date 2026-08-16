from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_harness import (
    AgentHarnessArtifact,
    AgentHarnessAttachment,
    AgentHarnessEntry,
    AgentHarnessRun,
    AgentHarnessSession,
)
from app.repositories.base import BaseRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.config import settings
from app.services.agent_harness.contracts import (
    ENTRY_PAYLOAD_TYPES,
    ActiveRunView,
    AgentCommand,
    AssistantDraftView,
    MessageCommand,
    OpenSessionRequest,
    PendingInteractionView,
    SessionSnapshot,
    SessionView,
    ToolProgressView,
)
from app.services.agent_harness.projection import (
    entry_contract,
    pending_interaction_entry_view,
    public_interaction_request,
    public_interaction_response,
    public_model_summary,
    run_view,
)
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentScopeRequest,
    resolve_environment_scope,
)
from app.services.agent_harness.environment_target import (
    remote_environment_target_snapshot,
)
from app.services.agent_harness.tool_projection import (
    public_error_message,
    public_result_details,
    public_tool_progress_view,
    public_tool_details,
)


ACTIVE_RUN_STATUSES = ("queued", "running", "waiting_user")
TERMINAL_RUN_STATUSES = ("completed", "failed", "cancelled")
_SESSION_SETTING_UNSET = object()


def _context_setting_changes(values: dict[str, object]) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    if "model_snapshot" in values:
        snapshot = values["model_snapshot"]
        target = snapshot.get("target") if isinstance(snapshot, dict) else None
        changes["model"] = (
            {
                "provider": str(target.get("provider_kind") or "unknown"),
                "model": str(target.get("model_name") or "unknown"),
            }
            if isinstance(target, dict)
            else None
        )
    for field in ("permission_mode", "workspace_access"):
        if field in values:
            changes[field] = str(values[field])
    if "environment_scope" in values:
        scope = values["environment_scope"]
        changes["environment_scope"] = dict(scope) if isinstance(scope, dict) else scope
    return changes


async def _turn_execution_config(
    db: AsyncSession,
    session: AgentHarnessSession,
    *,
    model_snapshot: dict | None = None,
) -> dict[str, Any]:
    requested_scope = session.environment_scope or {"mode": "auto"}
    metadata = session.session_metadata or {}
    stored_allow_remote = metadata.get("_allow_remote_environments")
    allow_remote = (
        stored_allow_remote
        if isinstance(stored_allow_remote, bool)
        else not settings.auth_is_team
    )
    connection_repository = RemoteConnectionRepository(db)
    authorized = await EnvironmentCatalog(connection_repository).list_authorized(
        workspace_id=str(session.workspace_id),
        allow_remote=allow_remote,
    )
    resolved_scope = resolve_environment_scope(
        EnvironmentScopeRequest(
            mode=("manual" if requested_scope.get("mode") == "manual" else "auto"),
            selected_environment_ids=tuple(
                str(item)
                for item in (requested_scope.get("environment_ids") or ())
                if isinstance(item, str) and item
            ),
        ),
        authorized,
    )
    environment_targets: dict[str, dict[str, Any]] = {}
    for environment in resolved_scope.environments.values():
        if environment.kind != "ssh":
            continue
        connection = await connection_repository.get_for_workspace(
            environment.environment_id,
            workspace_id=str(session.workspace_id),
        )
        if connection is not None:
            environment_targets[
                environment.environment_id
            ] = await remote_environment_target_snapshot(
                connection_repository,
                connection,
            )
    return {
        "settings_revision": int(session.settings_revision or 1),
        "model": model_snapshot or session.model_snapshot,
        "permission_mode": session.permission_mode,
        "workspace_access": session.workspace_access,
        "environment_scope": {
            "mode": resolved_scope.mode,
            "environment_ids": list(resolved_scope.environment_ids),
        },
        "environment_targets": environment_targets,
    }


@dataclass(frozen=True)
class RunFence:
    owner: str
    generation: int


class AgentHarnessAttachmentRepository(BaseRepository[AgentHarnessAttachment]):
    model = AgentHarnessAttachment

    async def get_owned(
        self,
        attachment_id: str,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessAttachment | None:
        return await self.session.scalar(
            select(self.model).where(
                self.model.id == attachment_id,
                self.model.session_id == session_id,
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
            )
        )

    async def get_owned_for_user(
        self,
        attachment_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessAttachment | None:
        return await self.session.scalar(
            select(self.model).where(
                self.model.id == attachment_id,
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
            )
        )

    async def list_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> list[AgentHarnessAttachment]:
        result = await self.session.execute(
            select(self.model)
            .where(
                self.model.session_id == session_id,
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
            )
            .order_by(self.model.created_at, self.model.id)
        )
        return list(result.scalars().all())

    async def search_for_session(
        self,
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
        query: str,
        limit: int,
    ) -> list[AgentHarnessAttachment]:
        if limit < 1:
            return []
        statement = select(self.model).where(
            self.model.session_id == session_id,
            self.model.workspace_id == workspace_id,
            self.model.user_id == user_id,
            self.model.status == "ready",
        )
        if query:
            escaped = (
                query.casefold()
                .replace("\\", "\\\\")
                .replace("%", "\\%")
                .replace("_", "\\_")
            )
            statement = statement.where(
                func.lower(self.model.filename).like(f"%{escaped}%", escape="\\")
            )
        result = await self.session.execute(
            statement.order_by(self.model.created_at, self.model.id).limit(limit)
        )
        return list(result.scalars().all())

    async def delete_owned(
        self,
        attachment_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ) -> bool:
        result = await self.session.execute(
            delete(self.model)
            .where(
                self.model.id == attachment_id,
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
            )
            .execution_options(synchronize_session="fetch")
        )
        await self.session.commit()
        for obj in list(self.session.identity_map.values()):
            if isinstance(obj, self.model) and str(obj.id) == attachment_id:
                self.session.expunge(obj)
        return bool(result.rowcount)

    async def mark_pending_delete_if_unreferenced(
        self,
        attachment_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ) -> str:
        """Atomically reserve an unreferenced attachment for physical deletion."""

        try:
            reservation = await self.session.execute(
                update(self.model)
                .where(
                    self.model.id == attachment_id,
                    self.model.workspace_id == workspace_id,
                    self.model.user_id == user_id,
                    self.model.status == "ready",
                )
                .values(status="pending_delete")
                .returning(self.model.session_id)
            )
            session_id = reservation.scalar_one_or_none()
            if session_id is None:
                await self.session.rollback()
                return "missing"
            await self.session.execute(
                update(AgentHarnessSession)
                .where(AgentHarnessSession.id == session_id)
                .values(history_revision=AgentHarnessSession.history_revision)
            )
            payloads = list(
                (
                    await self.session.execute(
                        select(AgentHarnessEntry.payload).where(
                            AgentHarnessEntry.session_id == session_id,
                            AgentHarnessEntry.type == "message",
                        )
                    )
                ).scalars()
            )
            if attachment_id in _referenced_attachment_ids(payloads):
                await self.session.rollback()
                return "referenced"
            await self.session.commit()
            return "reserved"
        except Exception:
            await self.session.rollback()
            raise

    async def require_ids_for_session(
        self,
        attachment_ids: Iterable[str],
        *,
        session_id: str,
        workspace_id: str,
        user_id: str,
    ) -> list[AgentHarnessAttachment]:
        ordered_ids = list(dict.fromkeys(attachment_ids))
        if not ordered_ids:
            return []
        result = await self.session.execute(
            select(self.model).where(
                self.model.id.in_(ordered_ids),
                self.model.session_id == session_id,
                self.model.workspace_id == workspace_id,
                self.model.user_id == user_id,
                self.model.status == "ready",
            )
        )
        found = {str(item.id): item for item in result.scalars().all()}
        if found.keys() != set(ordered_ids):
            raise LookupError("one or more attachments do not belong to the session")
        return [found[item_id] for item_id in ordered_ids]

    async def delete_orphans_before(self, cutoff: datetime) -> list[str]:
        try:
            initial = list(
                (
                    await self.session.execute(
                        select(self.model.session_id).where(
                            self.model.created_at < cutoff
                        )
                    )
                ).scalars()
            )
            session_ids = sorted({str(session_id) for session_id in initial})
            if not session_ids:
                return []
            for session_id in session_ids:
                await self.session.execute(
                    update(AgentHarnessSession)
                    .where(AgentHarnessSession.id == session_id)
                    .values(history_revision=AgentHarnessSession.history_revision)
                )
            rows = list(
                (
                    await self.session.execute(
                        select(
                            self.model.id,
                            self.model.session_id,
                            self.model.storage_path,
                        ).where(
                            self.model.created_at < cutoff,
                            self.model.session_id.in_(session_ids),
                        )
                    )
                ).all()
            )
            entries = list(
                (
                    await self.session.execute(
                        select(AgentHarnessEntry.payload).where(
                            AgentHarnessEntry.session_id.in_(session_ids),
                            AgentHarnessEntry.type == "message",
                        )
                    )
                ).scalars()
            )
            referenced = _referenced_attachment_ids(entries)
            orphans = [row for row in rows if str(row.id) not in referenced]
            if orphans:
                await self.session.execute(
                    delete(self.model).where(
                        self.model.id.in_([row.id for row in orphans])
                    )
                )
            await self.session.commit()
            return [row.storage_path for row in orphans]
        except Exception:
            await self.session.rollback()
            raise


def _referenced_attachment_ids(payloads: Iterable[Any]) -> set[str]:
    referenced: set[str] = set()
    for payload in payloads:
        if not isinstance(payload, dict):
            continue
        for part in payload.get("parts") or []:
            if (
                isinstance(part, dict)
                and part.get("type") in {"attachment_ref", "file_ref", "directory_ref"}
                and part.get("attachment_id") is not None
            ):
                referenced.add(str(part["attachment_id"]))
    return referenced


def _tool_result_call_id(payload: dict[str, Any]) -> str | None:
    for part in payload.get("parts") or []:
        if isinstance(part, dict) and part.get("type") == "tool_result":
            call_id = part.get("call_id")
            return str(call_id) if call_id else None
    return None


class AgentHarnessArtifactRepository(BaseRepository[AgentHarnessArtifact]):
    model = AgentHarnessArtifact

    async def create_for_run(
        self,
        *,
        session_id: str,
        run_id: str | None,
        fence: RunFence | None = None,
        commit: bool = True,
        **data: Any,
    ) -> AgentHarnessArtifact:
        try:
            if run_id is not None:
                if fence is None:
                    raise ValueError("artifact creation requires an Agent run fence")
                fenced = await self.session.execute(
                    update(AgentHarnessRun)
                    .where(
                        AgentHarnessRun.id == run_id,
                        AgentHarnessRun.session_id == session_id,
                        AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                        AgentHarnessRun.lease_owner == fence.owner,
                        AgentHarnessRun.lease_generation == fence.generation,
                    )
                    .values(lease_generation=AgentHarnessRun.lease_generation)
                )
                if not fenced.rowcount:
                    raise ValueError("stale Agent run fence rejected artifact creation")
            artifact = await self.add(
                session_id=session_id,
                run_id=run_id,
                **data,
            )
            if commit:
                await self.session.commit()
                await self.session.refresh(artifact)
            return artifact
        except Exception:
            await self.session.rollback()
            raise

    async def list_for_session(self, session_id: str) -> list[AgentHarnessArtifact]:
        result = await self.session.execute(
            select(self.model)
            .where(self.model.session_id == session_id)
            .order_by(self.model.created_at.desc(), self.model.id.desc())
        )
        return list(result.scalars().all())

    async def get_owned(
        self,
        artifact_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ) -> AgentHarnessArtifact | None:
        result = await self.session.execute(
            select(self.model)
            .join(
                AgentHarnessSession,
                AgentHarnessSession.id == self.model.session_id,
            )
            .where(
                self.model.id == artifact_id,
                AgentHarnessSession.workspace_id == workspace_id,
                AgentHarnessSession.user_id == user_id,
                AgentHarnessSession.status != "deleted",
            )
        )
        return result.scalar_one_or_none()


class AgentHarnessRepository:
    """The persistence seam used by the complete Agent Harness."""

    def __init__(self, session: AsyncSession):
        self.db = session
        self._run_fences: dict[str, RunFence] = {}

    def bind_run_fence(self, run_id: str, *, owner: str, generation: int) -> None:
        self._run_fences[run_id] = RunFence(owner=owner, generation=generation)

    def run_fence(self, run_id: str) -> RunFence | None:
        return self._run_fences.get(run_id)

    def _fence_predicates(self, run_id: str):
        fence = self._run_fences.get(run_id)
        if fence is None:
            return (AgentHarnessRun.lease_owner.is_(None),)
        return (
            AgentHarnessRun.lease_owner == fence.owner,
            AgentHarnessRun.lease_generation == fence.generation,
        )

    async def open_session(self, request: OpenSessionRequest) -> AgentHarnessSession:
        session = AgentHarnessSession(
            user_id=request.user_id,
            workspace_id=str(request.workspace_id),
            project_id=str(request.project_id) if request.project_id else None,
            title=request.title,
            model_snapshot=request.model,
            workspace_snapshot=request.workspace,
            permission_mode=request.permission_mode,
            workspace_access=request.workspace_access,
            environment_scope=request.environment_scope.model_dump(exclude_none=True),
            prompt_snapshot=request.prompt_snapshot,
            session_metadata=request.metadata,
            history_revision=0,
            command_queue=[],
            command_ids=[],
            status="active",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def get_session(self, session_id: str) -> AgentHarnessSession | None:
        return await self.db.get(AgentHarnessSession, session_id)

    async def list_sessions(
        self,
        *,
        user_id: str,
        workspace_id: str,
        include_archived: bool = False,
    ) -> list[AgentHarnessSession]:
        stmt = select(AgentHarnessSession).where(
            AgentHarnessSession.user_id == user_id,
            AgentHarnessSession.workspace_id == workspace_id,
            AgentHarnessSession.status != "deleted",
        )
        if not include_archived:
            stmt = stmt.where(AgentHarnessSession.status == "active")
        result = await self.db.execute(
            stmt.order_by(
                AgentHarnessSession.updated_at.desc(), AgentHarnessSession.id.desc()
            )
        )
        return list(result.scalars().all())

    async def update_session_settings(
        self,
        session_id: str,
        *,
        title: str | None | object = _SESSION_SETTING_UNSET,
        model_snapshot: dict | None | object = _SESSION_SETTING_UNSET,
        permission_mode: str | object = _SESSION_SETTING_UNSET,
        workspace_access: str | object = _SESSION_SETTING_UNSET,
        environment_scope: dict | object = _SESSION_SETTING_UNSET,
        status: str | object = _SESSION_SETTING_UNSET,
    ) -> AgentHarnessSession:
        values: dict[str, object] = {}
        if title is not _SESSION_SETTING_UNSET:
            values["title"] = title
        if model_snapshot is not _SESSION_SETTING_UNSET:
            values["model_snapshot"] = model_snapshot
        if permission_mode is not _SESSION_SETTING_UNSET:
            values["permission_mode"] = permission_mode
        if workspace_access is not _SESSION_SETTING_UNSET:
            values["workspace_access"] = workspace_access
        if environment_scope is not _SESSION_SETTING_UNSET:
            values["environment_scope"] = environment_scope
        if status is not _SESSION_SETTING_UNSET:
            values["status"] = status
        if not values:
            raise ValueError("at least one session setting is required")

        settings_fields = {
            "model_snapshot",
            "permission_mode",
            "workspace_access",
            "environment_scope",
        }
        context_setting_values = {
            key: value for key, value in values.items() if key in settings_fields
        }
        if context_setting_values:
            values["settings_revision"] = AgentHarnessSession.settings_revision + 1
        requires_idle_run = values.get("status") == "archived"
        stmt = update(AgentHarnessSession).where(
            AgentHarnessSession.id == session_id,
            AgentHarnessSession.status.in_(("active", "archived")),
        )
        if requires_idle_run:
            active_run_exists = (
                select(AgentHarnessRun.id)
                .where(
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                )
                .exists()
            )
            stmt = stmt.where(~active_run_exists)

        result = await self.db.execute(stmt.values(**values))
        if not result.rowcount:
            await self.db.rollback()
            session = await self.get_session(session_id)
            if session is None:
                raise LookupError(f"agent session not found: {session_id}")
            if session.status != "active":
                raise ValueError("agent session is not accepting changes")
            if requires_idle_run and await self.get_current_run(session_id):
                raise ValueError("archive status cannot change during an active run")
            raise ValueError("agent session settings were not updated")

        session = await self.get_session(session_id)
        assert session is not None
        await self.db.refresh(session)
        if context_setting_values:
            payload = ENTRY_PAYLOAD_TYPES["context_update"].model_validate(
                {
                    "settings_revision": session.settings_revision,
                    "changes": _context_setting_changes(context_setting_values),
                }
            )
            sequence = int(session.history_revision) + 1
            self.db.add(
                AgentHarnessEntry(
                    session_id=session_id,
                    run_id=None,
                    sequence=sequence,
                    type="context_update",
                    schema_version=2,
                    payload=payload.model_dump(mode="json"),
                )
            )
            session.history_revision = sequence
        await self.db.commit()
        await self.db.refresh(session)
        return session

    async def create_run(
        self, session_id: str, *, model_snapshot: dict | None = None
    ) -> AgentHarnessRun:
        session = await self.get_session(session_id)
        if session is None or session.status != "active":
            raise ValueError("agent session is not accepting new commands")
        if await self.get_current_run(session_id) is not None:
            raise ValueError("session already has an active run")
        run = AgentHarnessRun(
            session_id=session_id,
            status="queued",
            model_snapshot=model_snapshot or session.model_snapshot,
            turn_execution_config=await _turn_execution_config(
                self.db,
                session,
                model_snapshot=model_snapshot,
            ),
            command_queue=[],
            command_ids=[],
        )
        self.db.add(run)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def submit_user_command(
        self,
        session_id: str,
        command: MessageCommand,
        *,
        model_snapshot: dict | None = None,
    ) -> tuple[AgentHarnessRun | None, AgentHarnessEntry | None, bool]:
        """Durably submit one user command without exposing a partial Run."""

        if command.type != "message":
            raise ValueError("submit_user_command requires message")
        session = await self.get_session(session_id)
        if session is None or session.status != "active":
            raise LookupError(f"agent session not found: {session_id}")
        try:
            mutable = await self.db.execute(
                update(AgentHarnessSession)
                .where(
                    AgentHarnessSession.id == session_id,
                    AgentHarnessSession.status == "active",
                )
                .values(history_revision=AgentHarnessSession.history_revision)
            )
            if not mutable.rowcount:
                raise ValueError("agent session is closing")
            await self.db.refresh(session)
            command_ids = list(session.command_ids or [])
            if command.command_id in command_ids:
                await self.db.commit()
                return None, None, False

            payload = await self._user_message_payload(session, command)
            if session.title is None:
                generated_title = _conversation_title(payload)
                if generated_title is not None:
                    session.title = generated_title

            current = await self.get_current_run(session_id)
            if current is not None:
                session.command_ids = [*command_ids, command.command_id]
                session.command_queue = [
                    *(session.command_queue or []),
                    command.model_dump(mode="json"),
                ]
                await self.db.commit()
                await self.db.refresh(session)
                return None, None, True

            run = AgentHarnessRun(
                session_id=session_id,
                status="queued",
                model_snapshot=model_snapshot or session.model_snapshot,
                turn_execution_config=await _turn_execution_config(
                    self.db,
                    session,
                    model_snapshot=model_snapshot,
                ),
                command_queue=[],
                command_ids=[],
            )
            self.db.add(run)
            await self.db.flush()
            sequence = int(session.history_revision) + 1
            entry = AgentHarnessEntry(
                session_id=session_id,
                run_id=str(run.id),
                sequence=sequence,
                type="message",
                schema_version=2,
                payload=payload,
            )
            session.history_revision = sequence
            session.command_ids = [*command_ids, command.command_id]
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(run)
            await self.db.refresh(entry)
            return run, entry, True
        except Exception:
            await self.db.rollback()
            raise

    async def _user_message_payload(
        self,
        session: AgentHarnessSession,
        command: AgentCommand | dict[str, Any],
    ) -> dict[str, Any]:
        raw = command if isinstance(command, dict) else command.model_dump(mode="json")
        raw_parts = raw.get("parts")
        if not isinstance(raw_parts, list) or not raw_parts:
            raise ValueError("message command requires parts")
        attachment_ids = [
            str(item.get("attachment_id"))
            for item in raw_parts
            if isinstance(item, dict)
            and item.get("type") in {"attachment_ref", "file_ref", "directory_ref"}
            and item.get("attachment_id") is not None
        ]
        attachments = await AgentHarnessAttachmentRepository(
            self.db
        ).require_ids_for_session(
            attachment_ids,
            session_id=str(session.id),
            workspace_id=str(session.workspace_id),
            user_id=session.user_id,
        )
        attachments_by_id = {str(item.id): item for item in attachments}
        command_id = str(raw.get("command_id") or "message")
        parts: list[dict[str, Any]] = []
        for index, item in enumerate(raw_parts):
            if not isinstance(item, dict):
                raise ValueError("message command parts must be objects")
            part_id = f"input:{command_id}:{index}"
            part_type = item.get("type")
            if part_type == "text":
                parts.append({"id": part_id, "type": "text", "text": item["text"]})
            elif part_type == "attachment_ref":
                attachment_id = str(item["attachment_id"])
                attachment = attachments_by_id[attachment_id]
                parts.append(
                    {
                        "id": part_id,
                        "type": "attachment_ref",
                        "attachment_id": attachment_id,
                        "filename": attachment.filename,
                        "kind": attachment.kind,
                        "mime_type": attachment.mime_type,
                        "size_bytes": attachment.size_bytes,
                    }
                )
            elif part_type in {"file_ref", "directory_ref"}:
                attachment_id = item.get("attachment_id")
                if attachment_id is not None:
                    attachment = attachments_by_id[str(attachment_id)]
                    parts.append(
                        {
                            "id": part_id,
                            "type": part_type,
                            "label": attachment.filename,
                            "attachment_id": str(attachment.id),
                        }
                    )
                else:
                    parts.append(
                        {
                            "id": part_id,
                            "type": part_type,
                            "label": str(item["path"]),
                            "project_id": item["project_id"],
                            "path": item["path"],
                        }
                    )
            elif part_type == "workflow_ref":
                parts.append(
                    {
                        "id": part_id,
                        "type": "workflow_ref",
                        "workflow_id": item["workflow_id"],
                        "label": str(item["workflow_id"]),
                        "project_id": item.get("project_id"),
                    }
                )
            elif part_type == "run_ref":
                parts.append(
                    {
                        "id": part_id,
                        "type": "run_ref",
                        "run_id": item["run_id"],
                        "label": str(item["run_id"]),
                    }
                )
            else:
                raise ValueError(f"unsupported message part: {part_type}")
        return (
            ENTRY_PAYLOAD_TYPES["message"]
            .model_validate(
                {
                    "role": "user",
                    "parts": parts,
                }
            )
            .model_dump(mode="json")
        )

    async def get_run(self, run_id: str) -> AgentHarnessRun | None:
        return await self.db.get(AgentHarnessRun, run_id)

    async def get_current_run(self, session_id: str) -> AgentHarnessRun | None:
        result = await self.db.execute(
            select(AgentHarnessRun)
            .where(
                AgentHarnessRun.session_id == session_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
            )
            .order_by(AgentHarnessRun.created_at.desc(), AgentHarnessRun.id.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_latest_run(self, session_id: str) -> AgentHarnessRun | None:
        current = await self.get_current_run(session_id)
        if current is not None:
            return current
        result = await self.db.execute(
            select(AgentHarnessRun)
            .where(AgentHarnessRun.session_id == session_id)
            .order_by(
                func.coalesce(
                    AgentHarnessRun.completed_at,
                    AgentHarnessRun.started_at,
                    AgentHarnessRun.created_at,
                ).desc(),
                AgentHarnessRun.created_at.desc(),
                AgentHarnessRun.id.desc(),
            )
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def list_runs(self, session_id: str) -> list[AgentHarnessRun]:
        result = await self.db.execute(
            select(AgentHarnessRun)
            .where(AgentHarnessRun.session_id == session_id)
            .order_by(
                func.coalesce(
                    AgentHarnessRun.started_at,
                    AgentHarnessRun.completed_at,
                    AgentHarnessRun.created_at,
                ),
                AgentHarnessRun.created_at,
                AgentHarnessRun.id,
            )
        )
        return list(result.scalars().all())

    async def list_recoverable_runs(self) -> list[AgentHarnessRun]:
        result = await self.db.execute(
            select(AgentHarnessRun)
            .where(AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES))
            .order_by(AgentHarnessRun.created_at, AgentHarnessRun.id)
        )
        return list(result.scalars().all())

    async def list_sessions_with_queued_command(
        self, *, kind: str
    ) -> list[AgentHarnessSession]:
        result = await self.db.execute(
            select(AgentHarnessSession)
            .where(AgentHarnessSession.status == "active")
            .order_by(AgentHarnessSession.created_at, AgentHarnessSession.id)
        )
        return [
            session
            for session in result.scalars().all()
            if any(
                isinstance(command, dict) and command.get("type") == kind
                for command in session.command_queue or []
            )
        ]

    async def claim_run(
        self, run_id: str, *, owner: str, lease_expires_at: datetime
    ) -> int | None:
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                or_(
                    AgentHarnessRun.lease_owner.is_(None),
                    AgentHarnessRun.lease_expires_at.is_(None),
                    AgentHarnessRun.lease_expires_at <= now,
                    AgentHarnessRun.lease_owner == owner,
                ),
            )
            .values(
                lease_owner=owner,
                lease_generation=AgentHarnessRun.lease_generation + 1,
                lease_expires_at=lease_expires_at,
            )
            .returning(AgentHarnessRun.lease_generation)
        )
        await self.db.commit()
        generation = result.scalar_one_or_none()
        return int(generation) if generation is not None else None

    async def renew_run_lease(
        self,
        run_id: str,
        *,
        owner: str,
        generation: int,
        lease_expires_at: datetime,
    ) -> bool:
        result = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                AgentHarnessRun.lease_owner == owner,
                AgentHarnessRun.lease_generation == generation,
            )
            .values(lease_expires_at=lease_expires_at)
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def release_run_lease(self, run_id: str, *, owner: str) -> bool:
        result = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                AgentHarnessRun.lease_owner == owner,
            )
            .values(lease_owner=None, lease_expires_at=None)
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def update_run(self, run_id: str, **changes: Any) -> AgentHarnessRun:
        run = await self.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        requested_status = changes.get("status")
        now = datetime.now(timezone.utc)
        if requested_status == "running" and run.started_at is None:
            changes["started_at"] = now
        if requested_status in TERMINAL_RUN_STATUSES and run.completed_at is None:
            changes["completed_at"] = now
        allowed = {
            "status",
            "phase",
            "model_snapshot",
            "lease_owner",
            "lease_expires_at",
            "draft",
            "tool_progress",
            "checkpoint",
            "retry_count",
            "token_usage",
            "termination_reason",
            "error",
            "started_at",
            "completed_at",
        }
        unknown = changes.keys() - allowed
        if unknown:
            raise ValueError(f"unsupported run changes: {', '.join(sorted(unknown))}")
        if requested_status in TERMINAL_RUN_STATUSES:
            changes.update(
                checkpoint=None,
                draft=None,
                tool_progress=None,
                lease_owner=None,
                lease_expires_at=None,
            )
            allowed_statuses = ACTIVE_RUN_STATUSES
        else:
            allowed_statuses = ACTIVE_RUN_STATUSES
        public_run_fields = {
            "status",
            "phase",
            "started_at",
            "completed_at",
            "termination_reason",
            "error",
        }
        values = dict(changes)
        if public_run_fields.intersection(changes):
            values["revision"] = AgentHarnessRun.revision + 1
        result = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(allowed_statuses),
                *self._fence_predicates(run_id),
            )
            .values(**values)
        )
        if not result.rowcount:
            await self.db.commit()
            await self.db.refresh(run)
            raise ValueError("terminal Agent run cannot be reactivated")
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def update_tool_progress(
        self,
        run_id: str,
        *,
        call_id: str,
        name: str,
        status: str,
        group_id: str | None = None,
        execution_mode: str | None = None,
        arguments: dict[str, Any] | None = None,
        output_summary: str | None = None,
        error: str | None = None,
    ) -> ToolProgressView:
        run = await self.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        progress = [
            dict(item) for item in run.tool_progress or [] if isinstance(item, dict)
        ]
        existing = next(
            (item for item in progress if item.get("call_id") == call_id),
            None,
        )
        if existing is None:
            raise LookupError(f"tool progress not found: {call_id}")
        now = datetime.now(timezone.utc)
        source_arguments = (
            arguments
            if arguments is not None
            else existing.get("arguments")
            if isinstance(existing.get("arguments"), dict)
            else {}
        )
        public_output = public_error_message(output_summary)
        public_error = public_error_message(error)
        existing_details = [
            detail
            for detail in existing.get("public_details") or []
            if isinstance(detail, dict)
            and detail.get("kind") not in {"output", "error"}
        ]
        input_details = existing_details or [
            detail.model_dump(mode="json")
            for detail in public_tool_details(name, source_arguments)
        ]
        raw: dict[str, Any] = {
            **existing,
            "call_id": call_id,
            "group_id": existing["group_id"],
            "execution_mode": existing["execution_mode"],
            "name": name,
            "display_name": existing["display_name"],
            "category": existing["category"],
            "summary": existing["summary"],
            "arguments": {},
            "status": status,
            "revision": int(existing.get("revision") or 0) + 1,
            "public_details": [
                *input_details,
                *[
                    detail.model_dump(mode="json")
                    for detail in public_result_details(
                        output_summary=public_output,
                        error=public_error,
                    )
                ],
            ],
        }
        if public_output is not None:
            raw["output_summary"] = public_output
        if public_error is not None:
            raw["error"] = public_error
        if status == "running" and raw.get("started_at") is None:
            raw["started_at"] = now
        if status in {"completed", "failed", "blocked", "cancelled"}:
            raw["completed_at"] = now
        view = public_tool_progress_view(raw)
        stored = view.model_dump(mode="json")
        for index, item in enumerate(progress):
            if item.get("call_id") == call_id:
                progress[index] = stored
                break
        else:
            progress.append(stored)
        await self.update_run(run_id, tool_progress=progress)
        return view

    async def terminalize_run(self, run_id: str, **changes: Any) -> AgentHarnessRun:
        status = changes.get("status")
        if status not in TERMINAL_RUN_STATUSES:
            raise ValueError("terminalize_run requires a terminal status")
        now = datetime.now(timezone.utc)
        changes.update(
            completed_at=changes.get("completed_at") or now,
            checkpoint=None,
            draft=None,
            tool_progress=None,
            lease_owner=None,
            lease_expires_at=None,
        )
        result = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                *self._fence_predicates(run_id),
            )
            .values(revision=AgentHarnessRun.revision + 1, **changes)
        )
        if not result.rowcount:
            await self.db.rollback()
            run = await self.get_run(run_id)
            if run is None:
                raise LookupError(f"agent run not found: {run_id}")
            if run.status in ACTIVE_RUN_STATUSES:
                raise ValueError("stale Agent run fence rejected terminalization")
            return run
        await self.db.commit()
        run = await self.get_run(run_id)
        assert run is not None
        await self.db.refresh(run)
        return run

    async def cancel_run_with_history(
        self,
        session_id: str,
        *,
        run_id: str,
        reason: str,
        tool_calls: list[dict[str, Any]],
    ) -> tuple[list[AgentHarnessEntry], AgentHarnessRun]:
        session = await self.get_session(session_id)
        run = await self.get_run(run_id)
        if session is None or run is None or str(run.session_id) != session_id:
            raise LookupError("agent session or run not found")
        now = datetime.now(timezone.utc)
        try:
            terminalized = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(
                    revision=AgentHarnessRun.revision + 1,
                    status="cancelled",
                    phase=None,
                    termination_reason=reason,
                    completed_at=now,
                    cancel_requested_at=now,
                    cancel_reason=reason,
                    checkpoint=None,
                    draft=None,
                    tool_progress=None,
                    lease_owner=None,
                    lease_expires_at=None,
                )
            )
            if not terminalized.rowcount:
                await self.db.rollback()
                current = await self.get_run(run_id)
                if current is None:
                    raise LookupError(f"agent run not found: {run_id}")
                if current.status in ACTIVE_RUN_STATUSES:
                    raise ValueError("stale Agent run fence rejected cancellation")
                return [], current
            await self.db.refresh(session, with_for_update=True)
            resolved_result = await self.db.execute(
                select(AgentHarnessEntry.payload).where(
                    AgentHarnessEntry.session_id == session_id,
                    AgentHarnessEntry.run_id == run_id,
                    AgentHarnessEntry.type == "message",
                )
            )
            resolved_call_ids = {
                call_id
                for payload in resolved_result.scalars().all()
                if isinstance(payload, dict)
                and payload.get("role") == "tool"
                and (call_id := _tool_result_call_id(payload)) is not None
            }
            sequence = int(session.history_revision)
            committed: list[AgentHarnessEntry] = []
            for call in tool_calls:
                call_id = str(call.get("call_id") or "")
                if not call_id or call_id in resolved_call_ids:
                    continue
                payload = (
                    ENTRY_PAYLOAD_TYPES["message"]
                    .model_validate(
                        {
                            "role": "tool",
                            "parts": [
                                {
                                    "id": f"tool-result:{call_id}",
                                    "type": "tool_result",
                                    "call_id": call_id,
                                    "status": "cancelled",
                                    "output": {
                                        "type": "json",
                                        "value": {
                                            "error": {
                                                "code": "interrupted",
                                                "message": (
                                                    "Tool execution was interrupted by "
                                                    "user cancellation."
                                                ),
                                            }
                                        },
                                    },
                                    "error": (
                                        "Tool execution was interrupted by user "
                                        "cancellation."
                                    ),
                                }
                            ],
                        }
                    )
                    .model_dump(mode="json")
                )
                sequence += 1
                entry = AgentHarnessEntry(
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    type="message",
                    schema_version=2,
                    payload=payload,
                )
                self.db.add(entry)
                committed.append(entry)
            notice_payload = (
                ENTRY_PAYLOAD_TYPES["notice"]
                .model_validate(
                    {
                        "code": reason,
                        "message": "The Agent run was cancelled by the user.",
                    }
                )
                .model_dump(mode="json")
            )
            sequence += 1
            notice = AgentHarnessEntry(
                session_id=session_id,
                run_id=run_id,
                sequence=sequence,
                type="notice",
                schema_version=2,
                payload=notice_payload,
            )
            self.db.add(notice)
            committed.append(notice)
            session.history_revision = sequence
            await self.db.commit()
            for entry in committed:
                await self.db.refresh(entry)
            current = await self.get_run(run_id)
            assert current is not None
            await self.db.refresh(current)
            return committed, current
        except Exception:
            await self.db.rollback()
            raise

    async def enqueue_command(
        self, session_id: str, command: AgentCommand
    ) -> tuple[AgentHarnessRun | None, bool]:
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if session.status != "active":
            raise ValueError("agent session is closing")
        attachment_ids = [
            str(part.attachment_id)
            for part in getattr(command, "parts", [])
            if getattr(part, "type", None)
            in {"attachment_ref", "file_ref", "directory_ref"}
            and getattr(part, "attachment_id", None) is not None
        ]
        if attachment_ids:
            await AgentHarnessAttachmentRepository(self.db).require_ids_for_session(
                attachment_ids,
                session_id=session_id,
                workspace_id=str(session.workspace_id),
                user_id=session.user_id,
            )
        run = await self.get_current_run(session_id)
        if run is None and command.type == "steer":
            raise ValueError("there is no active run to steer")
        target: AgentHarnessSession | AgentHarnessRun
        if run is not None and command.type in {"steer", "respond", "cancel"}:
            target = run
            mutable = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run.id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    select(AgentHarnessSession.id)
                    .where(
                        AgentHarnessSession.id == session_id,
                        AgentHarnessSession.status == "active",
                    )
                    .exists(),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
        else:
            target = session
            mutable = await self.db.execute(
                update(AgentHarnessSession)
                .where(
                    AgentHarnessSession.id == session.id,
                    AgentHarnessSession.status == "active",
                )
                .values(history_revision=AgentHarnessSession.history_revision)
            )
        if not mutable.rowcount:
            await self.db.rollback()
            raise ValueError("agent session is closing")
        await self.db.refresh(target)
        command_ids = list(target.command_ids or [])
        if command.command_id in command_ids:
            return run, False
        command_ids.append(command.command_id)
        target.command_ids = command_ids
        queued_command = command.model_dump(mode="json")
        target.command_queue = [*(target.command_queue or []), queued_command]
        if run is not None and command.type == "cancel":
            target.cancel_requested_at = target.cancel_requested_at or datetime.now(
                timezone.utc
            )
            target.cancel_reason = str(getattr(command, "reason", None) or "cancelled")
        await self.db.commit()
        await self.db.refresh(target)
        return run, True

    async def dequeue_commands(
        self, run_id: str, *, kinds: Iterable[str] | None = None
    ) -> list[dict]:
        run = await self.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        fenced = await self.db.execute(
            update(AgentHarnessRun)
            .where(
                AgentHarnessRun.id == run_id,
                AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                *self._fence_predicates(run_id),
            )
            .values(lease_generation=AgentHarnessRun.lease_generation)
        )
        if not fenced.rowcount:
            await self.db.commit()
            raise ValueError("stale Agent run fence rejected command dequeue")
        await self.db.refresh(run)
        selected_kinds = set(kinds) if kinds is not None else None
        selected: list[dict] = []
        retained: list[dict] = []
        for command in run.command_queue or []:
            if selected_kinds is None or command.get("type") in selected_kinds:
                selected.append(command)
            else:
                retained.append(command)
        run.command_queue = retained
        await self.db.commit()
        return selected

    async def peek_commands(
        self, run_id: str, *, kinds: Iterable[str] | None = None
    ) -> list[dict]:
        """Read queued commands without acknowledging their durable delivery."""

        run = await self.get_run(run_id)
        if run is None:
            raise LookupError(f"agent run not found: {run_id}")
        selected_kinds = set(kinds) if kinds is not None else None
        return [
            dict(command)
            for command in run.command_queue or []
            if selected_kinds is None or command.get("type") in selected_kinds
        ]

    async def commit_steers_to_history(
        self, session_id: str, *, run_id: str
    ) -> list[AgentHarnessEntry]:
        """Atomically move queued steers into canonical history at a safe point."""

        session = await self.get_session(session_id)
        run = await self.get_run(run_id)
        if session is None or run is None or str(run.session_id) != session_id:
            raise LookupError("agent session or run not found")
        try:
            fenced = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
            if not fenced.rowcount:
                await self.db.rollback()
                raise ValueError(
                    "terminal Agent run or stale fence rejected steer commit"
                )
            await self.db.refresh(run)
            await self.db.refresh(session, with_for_update=True)
            selected: list[dict] = []
            retained: list[dict] = []
            for command in run.command_queue or []:
                if command.get("type") == "steer":
                    selected.append(command)
                else:
                    retained.append(command)
            if not selected:
                await self.db.commit()
                return []
            sequence = int(session.history_revision)
            entries: list[AgentHarnessEntry] = []
            for command in selected:
                payload = await self._user_message_payload(session, command)
                sequence += 1
                entry = AgentHarnessEntry(
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    type="message",
                    schema_version=2,
                    payload=payload,
                )
                self.db.add(entry)
                entries.append(entry)
            run.command_queue = retained
            session.history_revision = sequence
            await self.db.commit()
            for entry in entries:
                await self.db.refresh(entry)
            return entries
        except Exception:
            await self.db.rollback()
            raise

    async def commit_steers_or_complete_run(
        self, session_id: str, *, run_id: str
    ) -> tuple[list[AgentHarnessEntry], AgentHarnessRun]:
        """Commit queued steers or terminalize the Run in one fenced transaction."""

        session = await self.get_session(session_id)
        run = await self.get_run(run_id)
        if session is None or run is None or str(run.session_id) != session_id:
            raise LookupError("agent session or run not found")
        try:
            fenced = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
            if not fenced.rowcount:
                await self.db.rollback()
                current = await self.get_run(run_id)
                if current is None:
                    raise LookupError(f"agent run not found: {run_id}")
                if current.status in ACTIVE_RUN_STATUSES:
                    raise ValueError(
                        "stale Agent run fence rejected completion safe point"
                    )
                return [], current
            await self.db.refresh(run)
            await self.db.refresh(session, with_for_update=True)
            selected: list[dict] = []
            retained: list[dict] = []
            for command in run.command_queue or []:
                if command.get("type") == "steer":
                    selected.append(command)
                else:
                    retained.append(command)
            entries: list[AgentHarnessEntry] = []
            if selected:
                sequence = int(session.history_revision)
                for command in selected:
                    payload = await self._user_message_payload(session, command)
                    sequence += 1
                    entry = AgentHarnessEntry(
                        session_id=session_id,
                        run_id=run_id,
                        sequence=sequence,
                        type="message",
                        schema_version=2,
                        payload=payload,
                    )
                    self.db.add(entry)
                    entries.append(entry)
                run.command_queue = retained
                session.history_revision = sequence
            else:
                run.revision = int(run.revision) + 1
                run.status = "completed"
                run.phase = None
                run.termination_reason = "completed"
                run.completed_at = datetime.now(timezone.utc)
                run.checkpoint = None
                run.draft = None
                run.tool_progress = None
                run.lease_owner = None
                run.lease_expires_at = None
            await self.db.commit()
            for entry in entries:
                await self.db.refresh(entry)
            await self.db.refresh(run)
            return entries, run
        except Exception:
            await self.db.rollback()
            raise

    async def move_session_commands_to_run(
        self, session_id: str, run_id: str, *, kinds: Iterable[str]
    ) -> list[dict]:
        session = await self.get_session(session_id)
        run = await self.get_run(run_id)
        if session is None or run is None or str(run.session_id) != session_id:
            raise LookupError("agent session or run not found")
        await self.db.execute(
            update(AgentHarnessSession)
            .where(AgentHarnessSession.id == session_id)
            .values(history_revision=AgentHarnessSession.history_revision)
        )
        await self.db.execute(
            update(AgentHarnessRun)
            .where(AgentHarnessRun.id == run_id)
            .values(lease_generation=AgentHarnessRun.lease_generation)
        )
        await self.db.refresh(session)
        await self.db.refresh(run)
        selected_kinds = set(kinds)
        selected: list[dict] = []
        retained: list[dict] = []
        for command in session.command_queue or []:
            if command.get("type") in selected_kinds:
                selected.append(command)
            else:
                retained.append(command)
        session.command_queue = retained
        run.command_queue = [*(run.command_queue or []), *selected]
        run.command_ids = list(
            dict.fromkeys(
                [
                    *(run.command_ids or []),
                    *(item["command_id"] for item in selected),
                ]
            )
        )
        await self.db.commit()
        return selected

    async def create_run_from_next_session_command(
        self,
        session_id: str,
        *,
        kind: str,
        model_snapshot: dict | None = None,
    ) -> tuple[AgentHarnessRun, AgentHarnessEntry] | None:
        """Atomically consume one queued command, create its Run, and publish input."""

        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if session.status != "active":
            return None
        try:
            mutable = await self.db.execute(
                update(AgentHarnessSession)
                .where(
                    AgentHarnessSession.id == session_id,
                    AgentHarnessSession.status == "active",
                )
                .values(history_revision=AgentHarnessSession.history_revision)
            )
            if not mutable.rowcount:
                await self.db.commit()
                return None
            await self.db.refresh(session)
            if await self.get_current_run(session_id) is not None:
                await self.db.commit()
                return None
            queue = list(session.command_queue or [])
            index = next(
                (
                    position
                    for position, item in enumerate(queue)
                    if item.get("type") == kind
                ),
                None,
            )
            if index is None:
                await self.db.commit()
                return None
            command = queue.pop(index)
            payload = await self._user_message_payload(session, command)
            session.command_queue = queue
            run = AgentHarnessRun(
                session_id=session_id,
                status="queued",
                model_snapshot=model_snapshot or session.model_snapshot,
                turn_execution_config=await _turn_execution_config(
                    self.db,
                    session,
                    model_snapshot=model_snapshot,
                ),
                command_queue=[],
                command_ids=[],
            )
            self.db.add(run)
            await self.db.flush()
            sequence = int(session.history_revision) + 1
            entry = AgentHarnessEntry(
                session_id=session_id,
                run_id=str(run.id),
                sequence=sequence,
                type="message",
                schema_version=2,
                payload=payload,
            )
            session.history_revision = sequence
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(run)
            await self.db.refresh(entry)
            return run, entry
        except Exception:
            await self.db.rollback()
            raise

    async def delete_session(self, session_id: str) -> bool:
        result = await self.db.execute(
            delete(AgentHarnessSession).where(AgentHarnessSession.id == session_id)
        )
        await self.db.commit()
        return bool(result.rowcount)

    async def begin_session_closing(
        self,
        session_id: str,
        *,
        reason: str,
    ) -> AgentHarnessRun | None:
        """Persist the delete gate and request cancellation in one transaction."""

        now = datetime.now(timezone.utc)
        try:
            closing = await self.db.execute(
                update(AgentHarnessSession)
                .where(
                    AgentHarnessSession.id == session_id,
                    AgentHarnessSession.status.in_(("active", "archived", "closing")),
                )
                .values(
                    status="closing",
                    closing_requested_at=func.coalesce(
                        AgentHarnessSession.closing_requested_at, now
                    ),
                    closing_reason=reason,
                )
            )
            if not closing.rowcount:
                await self.db.rollback()
                raise LookupError(f"agent session not found: {session_id}")
            current = await self.get_current_run(session_id)
            if current is not None:
                await self.db.execute(
                    update(AgentHarnessRun)
                    .where(
                        AgentHarnessRun.id == current.id,
                        AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    )
                    .values(
                        cancel_requested_at=func.coalesce(
                            AgentHarnessRun.cancel_requested_at, now
                        ),
                        cancel_reason=reason,
                    )
                )
                await self.db.execute(
                    update(AgentHarnessRun)
                    .where(
                        AgentHarnessRun.id == current.id,
                        AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                        or_(
                            AgentHarnessRun.lease_owner.is_(None),
                            AgentHarnessRun.lease_expires_at.is_(None),
                            AgentHarnessRun.lease_expires_at <= now,
                            AgentHarnessRun.status == "waiting_user",
                        ),
                    )
                    .execution_options(synchronize_session=False)
                    .values(
                        status="cancelled",
                        phase=None,
                        termination_reason=reason,
                        completed_at=now,
                        checkpoint=None,
                        draft=None,
                        tool_progress=None,
                        lease_owner=None,
                        lease_expires_at=None,
                    )
                )
            await self.db.commit()
            if current is not None:
                await self.db.refresh(current)
            return current
        except Exception:
            await self.db.rollback()
            raise

    async def get_run_cancellation(self, run_id: str) -> str | None:
        result = await self.db.execute(
            select(
                AgentHarnessRun.status,
                AgentHarnessRun.cancel_requested_at,
                AgentHarnessRun.cancel_reason,
            ).where(AgentHarnessRun.id == run_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        if row.status in TERMINAL_RUN_STATUSES and row.status != "cancelled":
            return None
        if row.cancel_requested_at is None:
            return None
        return str(row.cancel_reason or "cancelled")

    async def append_entry(
        self,
        session_id: str,
        *,
        run_id: str | None,
        entry_type: str,
        payload: dict,
        schema_version: int = 2,
        entry_id: str | None = None,
    ) -> AgentHarnessEntry:
        payload_type = ENTRY_PAYLOAD_TYPES.get(entry_type)
        if payload_type is None:
            raise ValueError(f"unsupported history entry type: {entry_type}")
        validated_payload = payload_type.model_validate(payload).model_dump(mode="json")
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        if run_id is not None:
            fenced = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
            if not fenced.rowcount:
                await self.db.commit()
                raise ValueError(
                    "terminal Agent run or stale fence rejected history append"
                )
        # The session row is the serialization point. PostgreSQL locks it; SQLite
        # serializes the write transaction containing this read and increment.
        await self.db.refresh(session, with_for_update=True)
        sequence = int(session.history_revision) + 1
        entry_data = {
            "session_id": session_id,
            "run_id": run_id,
            "sequence": sequence,
            "type": entry_type,
            "schema_version": schema_version,
            "payload": validated_payload,
        }
        if entry_id is not None:
            entry_data["id"] = entry_id
        entry = AgentHarnessEntry(**entry_data)
        session.history_revision = sequence
        self.db.add(entry)
        await self.db.commit()
        await self.db.refresh(entry)
        return entry

    async def commit_plan(
        self,
        session_id: str,
        *,
        run_id: str,
        title: str | None,
        items: list[dict[str, Any]],
    ) -> AgentHarnessEntry:
        """Atomically replace the visible plan with the next durable revision."""

        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        try:
            fenced = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
            if not fenced.rowcount:
                raise ValueError(
                    "terminal Agent run or stale fence rejected plan update"
                )
            await self.db.refresh(session, with_for_update=True)
            latest = (
                await self.db.execute(
                    select(AgentHarnessEntry)
                    .where(
                        AgentHarnessEntry.session_id == session_id,
                        AgentHarnessEntry.run_id == run_id,
                        AgentHarnessEntry.type == "plan",
                    )
                    .order_by(AgentHarnessEntry.sequence.desc())
                    .limit(1)
                )
            ).scalar_one_or_none()
            revision = (
                int((latest.payload if latest is not None else {}).get("revision") or 0)
                + 1
            )
            plan_id = str(
                (latest.payload if latest is not None else {}).get("plan_id")
                or f"plan:{run_id}"
            )
            payload = (
                ENTRY_PAYLOAD_TYPES["plan"]
                .model_validate(
                    {
                        "plan_id": plan_id,
                        "revision": revision,
                        "title": title,
                        "items": items,
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                .model_dump(mode="json")
            )
            sequence = int(session.history_revision) + 1
            entry = AgentHarnessEntry(
                session_id=session_id,
                run_id=run_id,
                sequence=sequence,
                type="plan",
                schema_version=2,
                payload=payload,
            )
            session.history_revision = sequence
            self.db.add(entry)
            await self.db.commit()
            await self.db.refresh(entry)
            return entry
        except Exception:
            await self.db.rollback()
            raise

    async def commit_interaction_response(
        self,
        session_id: str,
        *,
        run_id: str,
        command_id: str | None,
        interaction_id: str,
        response: dict[str, Any],
    ) -> AgentHarnessEntry:
        """Persist one response and acknowledge its durable command atomically."""

        response_payload = (
            ENTRY_PAYLOAD_TYPES["interaction_response"]
            .model_validate(
                {
                    "interaction_id": interaction_id,
                    "response": public_interaction_response(response),
                }
            )
            .model_dump(mode="json")
        )
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        try:
            result = await self.db.execute(
                select(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .with_for_update()
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise ValueError("stale Agent run fence rejected interaction response")
            acknowledged_queue = self._acknowledge_respond_command(
                run.command_queue or [],
                command_id=command_id,
                interaction_id=interaction_id,
            )
            existing_result = await self.db.execute(
                select(AgentHarnessEntry)
                .where(
                    AgentHarnessEntry.session_id == session_id,
                    AgentHarnessEntry.run_id == run_id,
                    AgentHarnessEntry.type == "interaction_response",
                    AgentHarnessEntry.payload["interaction_id"].as_string()
                    == interaction_id,
                )
                .order_by(AgentHarnessEntry.sequence.desc())
                .limit(1)
            )
            entry = existing_result.scalar_one_or_none()
            if entry is None:
                await self.db.refresh(session, with_for_update=True)
                sequence = int(session.history_revision) + 1
                entry = AgentHarnessEntry(
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    type="interaction_response",
                    schema_version=2,
                    payload=response_payload,
                )
                self.db.add(entry)
                session.history_revision = sequence
            run.command_queue = acknowledged_queue
            await self.db.commit()
            await self.db.refresh(entry)
            return entry
        except Exception:
            await self.db.rollback()
            raise

    async def commit_waiting_interaction(
        self,
        session_id: str,
        *,
        run_id: str,
        request_payload: dict,
        checkpoint: dict,
        tool_progress: list[dict],
        notice_payload: dict | None = None,
    ) -> tuple[AgentHarnessEntry | None, AgentHarnessEntry, AgentHarnessRun]:
        """Atomically publish an interaction and make the Run wait for its answer."""

        public_request = public_interaction_request(request_payload["request"])
        request = (
            ENTRY_PAYLOAD_TYPES["interaction_request"]
            .model_validate(
                {
                    "interaction_id": request_payload["interaction_id"],
                    "request": public_request,
                }
            )
            .model_dump(mode="json")
        )
        notice = (
            ENTRY_PAYLOAD_TYPES["notice"]
            .model_validate(notice_payload)
            .model_dump(mode="json")
            if notice_payload is not None
            else None
        )
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        try:
            fenced = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(lease_generation=AgentHarnessRun.lease_generation)
            )
            if not fenced.rowcount:
                raise ValueError("stale Agent run fence rejected interaction")
            await self.db.refresh(session, with_for_update=True)
            sequence = int(session.history_revision)
            notice_entry: AgentHarnessEntry | None = None
            if notice is not None:
                sequence += 1
                notice_entry = AgentHarnessEntry(
                    session_id=session_id,
                    run_id=run_id,
                    sequence=sequence,
                    type="notice",
                    schema_version=2,
                    payload=notice,
                )
                self.db.add(notice_entry)
            sequence += 1
            request_entry = AgentHarnessEntry(
                session_id=session_id,
                run_id=run_id,
                sequence=sequence,
                type="interaction_request",
                schema_version=2,
                payload=request,
            )
            self.db.add(request_entry)
            session.history_revision = sequence
            durable_checkpoint = {**checkpoint, "history_revision": sequence}
            updated = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.status.in_(ACTIVE_RUN_STATUSES),
                    *self._fence_predicates(run_id),
                )
                .values(
                    revision=AgentHarnessRun.revision + 1,
                    status="waiting_user",
                    phase="interaction",
                    checkpoint=durable_checkpoint,
                    tool_progress=tool_progress,
                )
            )
            if not updated.rowcount:
                raise ValueError("stale Agent run fence rejected interaction")
            await self.db.commit()
            if notice_entry is not None:
                await self.db.refresh(notice_entry)
            await self.db.refresh(request_entry)
            run = await self.get_run(run_id)
            assert run is not None
            await self.db.refresh(run)
            return notice_entry, request_entry, run
        except Exception:
            await self.db.rollback()
            raise

    async def begin_approved_tool_execution(
        self,
        session_id: str,
        *,
        run_id: str,
        interaction_id: str,
        response: dict[str, Any],
        call: dict[str, Any],
        replay_policy: str,
        command_id: str | None = None,
    ) -> tuple[AgentHarnessEntry, AgentHarnessRun]:
        """Persist the accepted response and tool-start fence before execution."""

        response_payload = (
            ENTRY_PAYLOAD_TYPES["interaction_response"]
            .model_validate(
                {
                    "interaction_id": interaction_id,
                    "response": public_interaction_response(response),
                }
            )
            .model_dump(mode="json")
        )
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        try:
            result = await self.db.execute(
                select(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.session_id == session_id,
                    AgentHarnessRun.status == "waiting_user",
                    AgentHarnessRun.phase == "interaction",
                    *self._fence_predicates(run_id),
                )
                .with_for_update()
            )
            run = result.scalar_one_or_none()
            if run is None:
                raise ValueError("stale Agent run fence rejected tool execution")
            acknowledged_queue = self._acknowledge_respond_command(
                run.command_queue or [],
                command_id=command_id,
                interaction_id=interaction_id,
            )
            await self.db.refresh(session, with_for_update=True)
            sequence = int(session.history_revision) + 1
            response_entry = AgentHarnessEntry(
                session_id=session_id,
                run_id=run_id,
                sequence=sequence,
                type="interaction_response",
                schema_version=2,
                payload=response_payload,
            )
            self.db.add(response_entry)
            session.history_revision = sequence

            checkpoint = dict(run.checkpoint or {})
            in_flight_tools: list[dict[str, Any]] = []
            found_call = False
            for item in checkpoint.get("in_flight_tools") or []:
                if not isinstance(item, dict):
                    continue
                durable_item = dict(item)
                if durable_item.get("call_id") == call.get("call_id"):
                    durable_item.update(
                        replay_policy=replay_policy,
                        execution_started=True,
                    )
                    found_call = True
                in_flight_tools.append(durable_item)
            if not found_call:
                raise LookupError(
                    f"checkpoint tool call not found: {call.get('call_id') or 'unknown'}"
                )
            checkpoint.update(
                phase="tools",
                history_revision=sequence,
                in_flight_tools=in_flight_tools,
                interaction=None,
            )
            checkpoint.pop("waiting_call", None)
            checkpoint.pop("recovery_interaction", None)

            progress = [
                dict(item) for item in run.tool_progress or [] if isinstance(item, dict)
            ]
            existing = next(
                (
                    item
                    for item in progress
                    if item.get("call_id") == call.get("call_id")
                ),
                None,
            )
            if existing is None:
                raise LookupError(
                    f"tool progress not found: {call.get('call_id') or 'unknown'}"
                )
            call_id = str(call.get("call_id") or "")
            name = str(call.get("name") or "unknown")
            replacement = ToolProgressView.model_validate(
                {
                    **existing,
                    "call_id": call_id,
                    "group_id": existing["group_id"],
                    "execution_mode": existing["execution_mode"],
                    "name": name,
                    "display_name": existing["display_name"],
                    "category": existing["category"],
                    "summary": existing["summary"],
                    "arguments": existing.get("arguments") or {},
                    "status": "running",
                    "revision": int(existing.get("revision") or 0) + 1,
                    "started_at": existing.get("started_at")
                    or datetime.now(timezone.utc),
                }
            ).model_dump(mode="json")
            for index, item in enumerate(progress):
                if item.get("call_id") == call.get("call_id"):
                    progress[index] = replacement
                    break
            else:
                progress.append(replacement)

            updated = await self.db.execute(
                update(AgentHarnessRun)
                .where(
                    AgentHarnessRun.id == run_id,
                    AgentHarnessRun.status == "waiting_user",
                    AgentHarnessRun.phase == "interaction",
                    *self._fence_predicates(run_id),
                )
                .values(
                    revision=AgentHarnessRun.revision + 1,
                    status="running",
                    phase="tools",
                    checkpoint=checkpoint,
                    tool_progress=progress,
                    command_queue=acknowledged_queue,
                    started_at=run.started_at or datetime.now(timezone.utc),
                )
            )
            if not updated.rowcount:
                raise ValueError("stale Agent run fence rejected tool execution")
            await self.db.commit()
            await self.db.refresh(response_entry)
            await self.db.refresh(run)
            return response_entry, run
        except Exception:
            await self.db.rollback()
            raise

    async def get_interaction_response(
        self,
        session_id: str,
        *,
        run_id: str,
        interaction_id: str,
    ) -> dict[str, Any] | None:
        result = await self.db.execute(
            select(AgentHarnessEntry.payload)
            .where(
                AgentHarnessEntry.session_id == session_id,
                AgentHarnessEntry.run_id == run_id,
                AgentHarnessEntry.type == "interaction_response",
                AgentHarnessEntry.payload["interaction_id"].as_string()
                == interaction_id,
            )
            .order_by(AgentHarnessEntry.sequence.desc())
            .limit(1)
        )
        payload = result.scalar_one_or_none()
        if not isinstance(payload, dict):
            return None
        response = payload.get("response")
        return dict(response) if isinstance(response, dict) else None

    @staticmethod
    def _acknowledge_respond_command(
        queue: Iterable[dict[str, Any]],
        *,
        command_id: str | None,
        interaction_id: str,
    ) -> list[dict[str, Any]]:
        commands = [dict(item) for item in queue]
        if command_id is None:
            return commands
        if not any(
            item.get("type") == "respond"
            and item.get("command_id") == command_id
            and item.get("interaction_id") == interaction_id
            for item in commands
        ):
            raise ValueError("durable response command is no longer queued")
        return [item for item in commands if item.get("type") != "respond"]

    async def list_entries(
        self, session_id: str, *, after_sequence: int = 0, limit: int | None = None
    ) -> list[AgentHarnessEntry]:
        stmt = (
            select(AgentHarnessEntry)
            .where(
                AgentHarnessEntry.session_id == session_id,
                AgentHarnessEntry.sequence > after_sequence,
            )
            .order_by(AgentHarnessEntry.sequence)
        )
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def snapshot(self, session_id: str) -> SessionSnapshot:
        session = await self.get_session(session_id)
        if session is None:
            raise LookupError(f"agent session not found: {session_id}")
        runs = await self.list_runs(session_id)
        run = next(
            (item for item in reversed(runs) if item.status in ACTIVE_RUN_STATUSES),
            None,
        )
        entries = await self.list_entries(session_id)
        active_run = (
            ActiveRunView(
                run=run_view(run),
                assistant_draft=self._assistant_draft(run),
                tool_progress=self._tool_progress(run),
                pending_interaction=self._pending_interaction(run, entries),
            )
            if run is not None
            else None
        )
        return SessionSnapshot(
            session=SessionView.model_validate(
                {
                    "id": session.id,
                    "user_id": session.user_id,
                    "workspace_id": session.workspace_id,
                    "project_id": session.project_id,
                    "title": session.title,
                    "model": public_model_summary(session.model_snapshot),
                    "permission_mode": session.permission_mode,
                    "workspace_access": session.workspace_access,
                    "settings_revision": session.settings_revision,
                    "environment_scope": session.environment_scope or {"mode": "auto"},
                    "status": session.status,
                    "created_at": session.created_at,
                    "updated_at": session.updated_at,
                }
            ),
            runs=[run_view(item) for item in runs],
            entries=[
                entry_contract(entry)
                for entry in entries
                if entry.type not in {"compaction", "context_update"}
            ],
            active_run=active_run,
        )

    @staticmethod
    def _assistant_draft(run: AgentHarnessRun | None) -> AssistantDraftView | None:
        if run is None or not run.draft:
            return None
        return AssistantDraftView.model_validate(run.draft)

    @staticmethod
    def _tool_progress(run: AgentHarnessRun | None) -> list[ToolProgressView]:
        if run is None or not run.tool_progress:
            return []
        return [
            AgentHarnessRepository._public_tool_progress(item)
            for item in run.tool_progress
        ]

    @staticmethod
    def _public_tool_progress(item: Any) -> ToolProgressView:
        return public_tool_progress_view(item)

    @staticmethod
    def _pending_interaction(
        run: AgentHarnessRun | None,
        entries: list[AgentHarnessEntry],
    ) -> PendingInteractionView | None:
        if run is None or run.status != "waiting_user":
            return None
        pending: dict[str, AgentHarnessEntry] = {}
        for entry in entries:
            if str(entry.run_id) != str(run.id):
                continue
            interaction_id = str(entry.payload.get("interaction_id") or "")
            if not interaction_id:
                continue
            if entry.type == "interaction_request":
                pending[interaction_id] = entry
            elif entry.type == "interaction_response":
                pending.pop(interaction_id, None)
        if not pending:
            return None
        request = max(pending.values(), key=lambda item: item.sequence)
        return pending_interaction_entry_view(request)


def _conversation_title(payload: dict[str, Any]) -> str | None:
    for part in payload.get("parts") or []:
        if not isinstance(part, dict) or part.get("type") != "text":
            continue
        text = part.get("text")
        if not isinstance(text, str):
            continue
        compact = " ".join(text.strip().split()).strip("'\"`*_#> ")
        if not compact:
            continue
        if len(compact) <= 30:
            return compact
        candidate = compact[:30].rstrip(" ,.;:，。；：")
        if " " in candidate:
            boundary = candidate.rfind(" ")
            if boundary >= 12:
                candidate = candidate[:boundary]
        return candidate or compact[:30]
    return None


__all__ = [
    "AgentHarnessArtifactRepository",
    "AgentHarnessAttachmentRepository",
    "AgentHarnessRepository",
]
