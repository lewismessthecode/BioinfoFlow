from __future__ import annotations


def can_access_project(project, *, user_id: str | None, workspace_id: str | None) -> bool:
    if user_id is None:
        return True
    owner = str(getattr(project, "user_id", "") or "")
    if owner == "system" and user_id != "system":
        return False
    if owner == user_id:
        return True
    return bool(
        workspace_id and str(getattr(project, "workspace_id", "") or "") == workspace_id
    )


def can_access_run_project(
    project,
    *,
    user_id: str | None,
    workspace_id: str | None,
) -> bool:
    """Runs are owner-scoped even when projects are workspace-shared."""
    if user_id is None:
        return True
    if workspace_id and str(getattr(project, "workspace_id", "") or "") != workspace_id:
        return False
    owner = str(getattr(project, "user_id", "") or "")
    if owner == "system":
        return False
    return owner in {"", user_id}
