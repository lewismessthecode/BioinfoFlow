from __future__ import annotations

from collections.abc import Callable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_core.tools.remote import (
    RemoteConnectionResolver,
    SessionMetadataRemoteConnectionResolver,
)


ResolverFactory = Callable[[AsyncSession], RemoteConnectionResolver]


async def render_remote_connection_context(
    db: AsyncSession,
    agent_session,
    *,
    resolver_factory: ResolverFactory | None = None,
) -> str | None:
    connection_id = selected_remote_connection_id(agent_session)
    if not connection_id:
        return None
    resolver = (resolver_factory or SessionMetadataRemoteConnectionResolver)(db)
    try:
        connection = await resolver.get(
            connection_id,
            workspace_id=str(agent_session.workspace_id),
            user_id=str(agent_session.user_id),
            session_id=str(getattr(agent_session, "id", "")) or None,
        )
    except Exception:  # noqa: BLE001 - dynamic context must never break a turn
        return None

    lines = [
        "## Remote connection",
        f"- Selected remote connection: {connection.name} ({connection.id})",
        f"- SSH target: {connection.display_target}",
        f"- Status: {connection.status}",
        "- Prefer remote.read_file and remote.list_dir for read-only inspection.",
        "- remote.exec can run short diagnostics and is approval-gated as an elevated action.",
    ]
    if connection.skill_summary:
        lines.append(f"- Connection skill guidance: {connection.skill_summary}")
    return "\n".join(lines)


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
    if not isinstance(policy, dict):
        return None
    for key in (
        "remote_connection_id",
        "selected_remote_connection_id",
        "current_remote_connection_id",
    ):
        value = policy.get(key)
        if isinstance(value, str) and value:
            return value
    for key in ("remote_connection", "selected_remote_connection", "remote"):
        value = policy.get(key)
        if isinstance(value, dict):
            nested = value.get("id") or value.get("connection_id")
            if isinstance(nested, str) and nested:
                return nested
    return None
