from __future__ import annotations

from app.config import settings

ADMIN_ROLES = frozenset({"owner", "admin"})
SYSTEM_USER_ID = "system"


def is_team_mode() -> bool:
    return settings.auth_is_team


def is_system_owned_resource(owner_user_id: str | None) -> bool:
    return str(owner_user_id or "") == SYSTEM_USER_ID


def can_access_workspace_resource(
    *,
    resource_workspace_id: str | None,
    user_workspace_id: str | None,
    resource_owner_user_id: str | None = None,
    user_id: str | None = None,
) -> bool:
    if user_id is None:
        return True
    if is_system_owned_resource(resource_owner_user_id):
        return user_id == SYSTEM_USER_ID
    return bool(
        user_workspace_id
        and resource_workspace_id
        and str(resource_workspace_id) == str(user_workspace_id)
    )


def can_access_project(project, *, user_id: str | None, workspace_id: str | None) -> bool:
    return can_access_workspace_resource(
        resource_workspace_id=str(getattr(project, "workspace_id", "") or ""),
        user_workspace_id=workspace_id,
        resource_owner_user_id=str(getattr(project, "user_id", "") or ""),
        user_id=user_id,
    )


def can_access_run_project(
    project,
    *,
    user_id: str | None,
    workspace_id: str | None,
) -> bool:
    return can_access_project(project, user_id=user_id, workspace_id=workspace_id)


def can_manage_workspace_members(role: str | None) -> bool:
    return settings.auth_enabled_effective and settings.auth_is_team and role in ADMIN_ROLES


def can_manage_external_roots(role: str | None) -> bool:
    if not settings.auth_is_team:
        return True
    return role in ADMIN_ROLES


def can_perform_destructive_business_action(role: str | None) -> bool:
    if not settings.auth_is_team:
        return True
    return role in ADMIN_ROLES
