from __future__ import annotations

import posixpath
from pathlib import PurePosixPath
from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.path_layout import ensure_project_layout
from app.repositories.project_repo import ProjectRepository
from app.repositories.remote_connection_repo import RemoteConnectionRepository
from app.utils.exceptions import NotFoundError, ValidationError
from app.utils.repo_paths import normalize_repo_path


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)

    async def get_or_create_default(
        self, *, workspace_id: str, workspace_slug: str, user_id: str
    ):
        """Return the workspace default project, creating it if needed."""
        del workspace_slug

        existing = await self.repo.get_default_for_workspace(workspace_id)
        if existing:
            return existing
        project_id = str(uuid4())
        ensure_project_layout(project_id)
        try:
            return await self.repo.create(
                id=project_id,
                name="Recent",
                description="Uncategorized analyses",
                storage_mode="managed",
                external_root_path=None,
                user_id=user_id,
                created_by_user_id=user_id,
                workspace_id=workspace_id,
                is_default=True,
            )
        except IntegrityError:
            # Concurrent create — unique partial index blocked the duplicate.
            await self.repo.session.rollback()
            return await self.repo.get_default_for_workspace(workspace_id)

    async def list_projects(
        self,
        *,
        workspace_id: str,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
    ):
        return await self.repo.list(
            limit=limit, cursor=cursor, search=search, workspace_id=workspace_id
        )

    async def get_project(self, project_id: str, *, workspace_id: str | None = None):
        project = await self.repo.get(project_id)
        if project and workspace_id:
            if str(project.workspace_id) != workspace_id:
                return None
            if str(getattr(project, "user_id", "") or "") == "system":
                return None
        return project

    async def create_project(self, data: dict, *, user_id: str):
        data["user_id"] = user_id
        data.setdefault("created_by_user_id", user_id)
        project_id = str(data.get("id") or uuid4())
        if data.get("remote_connection_id") or data.get("remote_root_path"):
            await self._configure_remote_project(data)
        else:
            override_path = data.get("external_root_path")
            data["remote_connection_id"] = None
            data["remote_root_path"] = None
            if override_path:
                normalized_override = normalize_repo_path(str(override_path))
                data["storage_mode"] = "external"
                data["external_root_path"] = normalized_override
                ensure_project_layout(project_id, external_root_path=normalized_override)
            else:
                data["storage_mode"] = "managed"
                data["external_root_path"] = None
                ensure_project_layout(project_id)
        data["id"] = project_id
        return await self.repo.create(**data)

    async def update_project(self, project, data: dict):
        if "remote_connection_id" in data or "remote_root_path" in data:
            data.setdefault("remote_connection_id", getattr(project, "remote_connection_id", None))
            data.setdefault("remote_root_path", getattr(project, "remote_root_path", None))
            data.setdefault("workspace_id", str(project.workspace_id))
            await self._configure_remote_project(data)
        elif data.get("external_root_path"):
            normalized_override = normalize_repo_path(
                str(data["external_root_path"])
            )
            data["storage_mode"] = "external"
            data["external_root_path"] = normalized_override
            data["remote_connection_id"] = None
            data["remote_root_path"] = None
            ensure_project_layout(str(project.id), external_root_path=normalized_override)
        elif data.get("storage_mode") == "managed":
            data["external_root_path"] = None
            data["remote_connection_id"] = None
            data["remote_root_path"] = None
            ensure_project_layout(str(project.id))
        data.pop("workspace_id", None)
        return await self.repo.update(project, **data)

    async def delete_project(self, project):
        await self.repo.delete(project)

    async def _configure_remote_project(self, data: dict) -> None:
        connection_id = data.get("remote_connection_id")
        remote_root_path = data.get("remote_root_path")
        if not connection_id or not remote_root_path:
            raise ValidationError(
                "remote_connection_id and remote_root_path are required for remote projects"
            )
        if data.get("external_root_path"):
            raise ValidationError("remote projects cannot also set external_root_path")
        workspace_id = str(data.get("workspace_id") or "")
        if not workspace_id:
            raise ValidationError("workspace_id is required for remote projects")
        connection = await RemoteConnectionRepository(self.repo.session).get_for_workspace(
            str(connection_id),
            workspace_id=workspace_id,
        )
        if connection is None:
            raise NotFoundError("Remote connection not found")
        data["storage_mode"] = "remote"
        data["external_root_path"] = None
        data["remote_connection_id"] = str(connection.id)
        data["remote_root_path"] = normalize_remote_root_path(str(remote_root_path))


def normalize_remote_root_path(value: str) -> str:
    normalized = str(value or "").strip().replace("\\", "/")
    if not normalized:
        raise ValidationError("remote_root_path must be a non-empty absolute path")
    if "\x00" in normalized:
        raise ValidationError("remote_root_path contains an invalid character")
    if not PurePosixPath(normalized).is_absolute():
        raise ValidationError("remote_root_path must be an absolute POSIX path")
    normalized = posixpath.normpath(normalized)
    if normalized == ".":
        raise ValidationError("remote_root_path must be an absolute POSIX path")
    return normalized
