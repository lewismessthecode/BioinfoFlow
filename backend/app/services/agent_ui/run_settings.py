from __future__ import annotations

from typing import Any, TypedDict

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.agent_harness.contracts import MessageCommand, PermissionMode
from app.services.agent_harness.factory import resolve_model_snapshot
from app.services.agent_ui.execution_targets import (
    execution_runtime_target_snapshots,
    execution_target_catalog,
    normalize_execution_scope,
    selected_execution_targets,
)
from app.utils.exceptions import BadRequestError


class FrozenRunSettingsSnapshot(TypedDict):
    model_snapshot: dict[str, Any]
    permission_mode: PermissionMode
    execution_scope: dict[str, Any]
    allowed_targets: list[dict[str, Any]]
    _runtime_targets: list[dict[str, Any]]


async def freeze_message_run_settings(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    session: Any,
    command: MessageCommand,
) -> FrozenRunSettingsSnapshot:
    requested = command.run_settings
    model_selection = _message_model_selection(command)
    model_snapshot = (
        await resolve_model_snapshot(
            db,
            workspace_id=workspace_id,
            user_id=user_id,
            selection=model_selection,
        )
        if model_selection is not None
        else session.model_snapshot
    )
    if not isinstance(model_snapshot, dict):
        raise BadRequestError("Agent model selection is unavailable")

    project_id = str(session.project_id) if session.project_id else None
    targets, default_scope = await execution_target_catalog(
        db,
        workspace_id=workspace_id,
        user_id=user_id,
        project_id=project_id,
    )
    current_scope = session.execution_scope or default_scope.model_dump(mode="json")
    scope = normalize_execution_scope(
        requested.execution_scope if requested else current_scope,
        targets=targets,
        default=default_scope,
    )
    allowed_targets = selected_execution_targets(scope, targets)
    runtime_targets = await execution_runtime_target_snapshots(
        db,
        workspace_id=workspace_id,
        workspace_snapshot=session.workspace_snapshot or {},
        targets=allowed_targets,
    )
    permission_mode = (
        requested.permission_mode
        if requested and requested.permission_mode is not None
        else session.permission_mode
    )
    return {
        "model_snapshot": model_snapshot,
        "permission_mode": permission_mode,
        "execution_scope": scope.model_dump(mode="json"),
        "allowed_targets": [target.model_dump(mode="json") for target in allowed_targets],
        "_runtime_targets": runtime_targets,
    }


def _message_model_selection(command: MessageCommand) -> dict[str, str] | None:
    selection = command.run_settings.model if command.run_settings else None
    if selection is None:
        return None
    if selection.model_id:
        return {"model_id": str(selection.model_id)}
    if selection.profile_id:
        return {"profile_id": str(selection.profile_id)}
    if selection.provider and selection.model:
        return {"provider": selection.provider, "model": selection.model}
    return None


__all__ = ["FrozenRunSettingsSnapshot", "freeze_message_run_settings"]
