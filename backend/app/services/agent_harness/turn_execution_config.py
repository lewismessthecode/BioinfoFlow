from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.agent_harness import AgentHarnessSession
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_harness.environment_catalog import EnvironmentCatalog
from app.services.agent_harness.environment_scope import (
    EnvironmentScopeRequest,
    resolve_environment_scope,
)
from app.services.agent_harness.environment_target import (
    remote_environment_target_snapshot,
)


async def resolve_turn_execution_config(
    db: AsyncSession,
    session: AgentHarnessSession,
    *,
    model_snapshot: dict | None = None,
) -> dict[str, Any]:
    """Freeze the effective settings and authorized environments for one Run."""

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


__all__ = ["resolve_turn_execution_config"]
