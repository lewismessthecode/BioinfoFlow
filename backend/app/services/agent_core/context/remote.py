from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_repo import ProjectRepository
from app.services.agent_core.execution_target import selected_remote_connection_ids_from_policy
from app.services.agent_core.tools.remote import (
    RemoteConnectionResolver,
    SessionMetadataRemoteConnectionResolver,
)


ResolverFactory = Callable[[AsyncSession], RemoteConnectionResolver]


async def render_remote_connection_context(
    db: AsyncSession,
    agent_session,
    *,
    execution_target: dict[str, str] | None = None,
    resolver_factory: ResolverFactory | None = None,
) -> str | None:
    remote_project = await selected_remote_project(db, agent_session)
    connection_id = _selected_id_from_policy(
        {"execution_target": execution_target}
        if execution_target is not None
        else getattr(agent_session, "session_metadata", None)
    )
    if not connection_id:
        connection_id = selected_remote_connection_id(agent_session)
    if not connection_id and remote_project:
        connection_id = str(remote_project.remote_connection_id)
    if not connection_id:
        return None
    if remote_project and str(remote_project.remote_connection_id) != connection_id:
        remote_project = None
    resolver = (resolver_factory or SessionMetadataRemoteConnectionResolver)(db)
    try:
        connection = await resolver.get(
            connection_id,
            workspace_id=str(agent_session.workspace_id),
            user_id=str(agent_session.user_id),
            session_id=str(getattr(agent_session, "id", "")) or None,
        )
    except Exception:  # noqa: BLE001 - dynamic context must never break a turn
        return "\n".join(
            [
                "## Remote connection",
                f"- Target connection ID: {connection_id}",
                "- Status: unavailable",
                "- Connection details could not be resolved for the current target.",
            ]
        )

    lines = [
        "## Remote connection",
        f"- Selected remote connection: {connection.name} ({connection.id})",
        f"- SSH target: {connection.display_target}",
        f"- Status: {connection.status}",
        "- Prefer remote.read_file and remote.list_dir for read-only inspection.",
        (
            "- remote.exec runs approval-gated bounded remote commands for diagnostics "
            "and operational CLIs; each call retains timeout and output limits."
        ),
    ]
    if remote_project:
        lines.extend(
            [
                f"- Remote project: {remote_project.name} ({remote_project.id})",
                f"- Remote working directory: {remote_project.remote_root_path}",
                "- Treat relative remote paths and shell commands as scoped to this remote working directory.",
            ]
        )
    if connection.skill_summary:
        lines.append(f"- Connection skill guidance: {connection.skill_summary}")
    return "\n".join(lines)


async def selected_remote_project(db: AsyncSession, agent_session):
    project_id = getattr(agent_session, "project_id", None)
    if not project_id:
        return None
    try:
        project = await ProjectRepository(db).get_fresh(str(project_id))
    except Exception:  # noqa: BLE001 - dynamic context must never break a turn
        return None
    if not project or getattr(project, "storage_mode", None) != "remote":
        return None
    if not getattr(project, "remote_connection_id", None):
        return None
    return project


def selected_remote_connection_id(agent_session) -> str | None:
    for policy in (
        getattr(agent_session, "session_metadata", None),
        getattr(agent_session, "context_policy", None),
        getattr(agent_session, "toolset_policy", None),
    ):
        value = _selected_id_from_policy(policy)
        if value:
            return value
    return None


def _selected_id_from_policy(policy: Any) -> str | None:
    for connection_id in selected_remote_connection_ids_from_policy(policy):
        return connection_id
    return None
