from __future__ import annotations

import posixpath
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.agent_core import AgentSession
from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_core.execution_target import execution_target_from_session


_UNSET = object()


@dataclass(frozen=True)
class RemoteBoundary:
    connection_id: str | None
    effective_root: str | None
    root_source: str
    remote_identity: dict[str, Any] | None
    resource_revisions: dict[str, dict[str, str | None]]

    def audit_boundary(self) -> dict[str, Any]:
        return {
            "kind": "remote_ssh",
            "enforcement": "remote_account",
            "sandboxed": False,
            "structured_remote_tools": {
                "effective_root": self.effective_root,
                "enforcement": (
                    "lexical_path_validation_and_remote_realpath_guard"
                    if self.effective_root
                    else "none"
                ),
            },
            "remote_exec": {
                "working_directory": self.effective_root,
                "shell_root_confinement": False,
            },
        }

    def policy_fingerprint(self) -> tuple[Any, ...]:
        metadata_root = self.effective_root if self.root_source == "metadata" else None
        return (
            metadata_root,
            bool(metadata_root),
            False,
        )


class RemoteBoundaryResolver:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def resolve(
        self,
        *,
        agent_session: AgentSession,
        connection_id: str | None = None,
        session_metadata: Any = _UNSET,
    ) -> RemoteBoundary:
        selected_connection_id = connection_id or execution_target_from_session(
            agent_session
        ).get("connection_id")
        remote_identity: dict[str, Any] | None = None
        revisions: dict[str, dict[str, str | None]] = {}
        if selected_connection_id and _is_uuid(selected_connection_id):
            connection = await RemoteConnectionRepository(
                self.session
            ).get_for_workspace(
                selected_connection_id,
                workspace_id=str(agent_session.workspace_id),
            )
            if connection is not None:
                remote_identity = {
                    "connection_id": str(connection.id),
                    "name": str(connection.name),
                    "host": str(connection.host),
                    "port": int(connection.port),
                    "username": str(connection.username),
                }
                revisions["remote_connection"] = _resource_revision(connection)

        project = await _fresh_remote_project(
            self.session,
            agent_session=agent_session,
            connection_id=selected_connection_id,
        )
        if project is not None:
            effective_root = _bounded_remote_root(project.remote_root_path)
            root_source = "project" if effective_root else "none"
        else:
            effective_root = _metadata_remote_root(
                agent_session.session_metadata
                if session_metadata is _UNSET
                else session_metadata
            )
            root_source = "metadata" if effective_root else "none"
        if project is not None:
            revisions["project"] = _resource_revision(project)
        return RemoteBoundary(
            connection_id=selected_connection_id,
            effective_root=effective_root,
            root_source=root_source,
            remote_identity=remote_identity,
            resource_revisions=revisions,
        )


async def _fresh_remote_project(
    session: AsyncSession,
    *,
    agent_session: AgentSession,
    connection_id: str | None,
):
    if not agent_session.project_id or not connection_id:
        return None
    project = await ProjectRepository(session).get_fresh(str(agent_session.project_id))
    if project is None:
        return None
    if str(project.workspace_id) != str(agent_session.workspace_id):
        return None
    if str(project.storage_mode) != "remote":
        return None
    if str(project.remote_connection_id) != str(connection_id):
        return None
    return project


def _metadata_remote_root(metadata: Any) -> str | None:
    if not isinstance(metadata, dict):
        return None
    for key in ("remote_project_root", "remote_root_path"):
        root = _bounded_remote_root(metadata.get(key))
        if root:
            return root
    execution_target = metadata.get("execution_target")
    if isinstance(execution_target, dict):
        for key in ("remote_project_root", "remote_root_path"):
            root = _bounded_remote_root(execution_target.get(key))
            if root:
                return root
    return None


def _bounded_remote_root(value: Any) -> str | None:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 1000
        or "\x00" in value
    ):
        return None
    normalized = posixpath.normpath(value.strip())
    if not normalized.startswith("/") or normalized == "/":
        return None
    return normalized


def _resource_revision(resource: Any) -> dict[str, str | None]:
    updated_at = getattr(resource, "updated_at", None)
    return {
        "id": str(resource.id),
        "updated_at": updated_at.isoformat() if updated_at is not None else None,
    }


def _is_uuid(value: str) -> bool:
    try:
        UUID(str(value))
    except (TypeError, ValueError):
        return False
    return True
