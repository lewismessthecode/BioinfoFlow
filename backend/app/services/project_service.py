from __future__ import annotations

from uuid import uuid4

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.path_layout import ensure_project_layout
from app.repositories.project_repo import ProjectRepository
from app.utils.repo_paths import normalize_repo_path


class ProjectService:
    def __init__(self, session: AsyncSession):
        self.repo = ProjectRepository(session)

    async def get_or_create_default(
        self, *, workspace_id: str, workspace_slug: str, user_id: str
    ):
        """Return the workspace default project, creating it if needed."""
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
        override_path = data.get("external_root_path")
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
        if data.get("external_root_path"):
            normalized_override = normalize_repo_path(
                str(data["external_root_path"])
            )
            data["storage_mode"] = "external"
            data["external_root_path"] = normalized_override
            ensure_project_layout(str(project.id), external_root_path=normalized_override)
        elif data.get("storage_mode") == "managed":
            data["external_root_path"] = None
            ensure_project_layout(str(project.id))
        return await self.repo.update(project, **data)

    async def delete_project(self, project):
        await self.repo.delete(project)
