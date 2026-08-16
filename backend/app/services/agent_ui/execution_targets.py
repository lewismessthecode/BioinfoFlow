from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.services.agent_ui.contracts import (
    ExecutionScopeSelection,
    ExecutionTargetView,
)
from app.utils.authorization import can_access_project
from app.utils.exceptions import NotFoundError


LOCAL_TARGET_ID = "local"
LOCAL_TARGET_HANDLE = "local"
_TARGET_HANDLE_PATTERN = re.compile(r"[^a-z0-9]+")


async def execution_target_catalog(
    db: AsyncSession,
    *,
    workspace_id: str,
    user_id: str,
    project_id: str | None,
) -> tuple[list[ExecutionTargetView], ExecutionScopeSelection]:
    project = None
    if project_id:
        project = await ProjectRepository(db).get(project_id)
        if (
            project is None
            or str(project.workspace_id) != workspace_id
            or not can_access_project(
                project,
                user_id=user_id,
                workspace_id=workspace_id,
            )
        ):
            raise NotFoundError(f"Project not found: {project_id}")

    if project is not None and project.storage_mode == "remote":
        connection_id = str(project.remote_connection_id or "")
        if not connection_id:
            raise ValueError("remote project is missing its connection")
        connection = await RemoteConnectionRepository(db).get_for_workspace(
            connection_id,
            workspace_id=workspace_id,
        )
        if connection is None:
            raise NotFoundError(f"Remote connection not found: {connection_id}")
        target = _remote_target(connection, primary=True, index=1)
        return [target], ExecutionScopeSelection(
            mode="manual",
            target_ids=[target.id],
        )

    connections, _pagination = await RemoteConnectionRepository(db).list_for_workspace(
        workspace_id=workspace_id,
        limit=100,
    )
    targets = [
        ExecutionTargetView(
            id=LOCAL_TARGET_ID,
            handle=LOCAL_TARGET_HANDLE,
            alias="Local",
            kind="local",
            status="online",
            primary=True,
        ),
        *(
            _remote_target(connection, primary=False, index=index)
            for index, connection in enumerate(connections, start=1)
        ),
    ]
    return targets, ExecutionScopeSelection(mode="auto")


def normalize_execution_scope(
    value: ExecutionScopeSelection | dict[str, Any] | None,
    *,
    targets: Iterable[ExecutionTargetView],
    default: ExecutionScopeSelection,
) -> ExecutionScopeSelection:
    selection = (
        value
        if isinstance(value, ExecutionScopeSelection)
        else ExecutionScopeSelection.model_validate(value)
        if value is not None
        else default
    )
    target_list = list(targets)
    known_ids = {target.id for target in target_list if target.disabled_reason is None}
    if selection.mode == "auto":
        if len(target_list) == 1 and target_list[0].kind == "remote_ssh":
            return ExecutionScopeSelection(
                mode="manual",
                target_ids=[target_list[0].id],
            )
        return ExecutionScopeSelection(mode="auto")

    selected = [target_id for target_id in selection.target_ids if target_id in known_ids]
    if not selected:
        raise ValueError("manual execution scope has no available targets")
    if len(target_list) == 1 and target_list[0].kind == "remote_ssh":
        selected = [target_list[0].id]
    return ExecutionScopeSelection(mode="manual", target_ids=selected)


def selected_execution_targets(
    selection: ExecutionScopeSelection,
    targets: Iterable[ExecutionTargetView],
) -> list[ExecutionTargetView]:
    target_list = [target for target in targets if target.disabled_reason is None]
    if selection.mode == "auto":
        return target_list
    selected_ids = set(selection.target_ids)
    return [target for target in target_list if target.id in selected_ids]


def _remote_target(connection, *, primary: bool, index: int) -> ExecutionTargetView:
    alias = str(connection.name or "").strip() or str(connection.ssh_alias or "").strip()
    if not alias:
        alias = f"Remote {index}"
    return ExecutionTargetView(
        id=str(connection.id),
        handle=_target_handle(alias, str(connection.id)),
        alias=alias,
        kind="remote_ssh",
        status=(
            connection.last_status
            if connection.last_status in {"online", "offline", "error", "unknown"}
            else "unknown"
        ),
        primary=primary,
    )


def _target_handle(alias: str, connection_id: str) -> str:
    slug = _TARGET_HANDLE_PATTERN.sub("-", alias.lower()).strip("-")
    suffix = connection_id.replace("-", "")[:8]
    return f"ssh:{slug or 'remote'}-{suffix}"


__all__ = [
    "LOCAL_TARGET_HANDLE",
    "LOCAL_TARGET_ID",
    "execution_target_catalog",
    "normalize_execution_scope",
    "selected_execution_targets",
]
