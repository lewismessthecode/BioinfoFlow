from __future__ import annotations

from sqlalchemy import desc, or_, select

from app.models.project import Project
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class ProjectRepository(BaseRepository[Project]):
    model = Project

    async def get_default_for_workspace(self, workspace_id: str) -> Project | None:
        """Get the workspace default (uncategorized) project."""
        stmt = (
            select(self.model)
            .where(
                self.model.workspace_id == workspace_id,
                self.model.is_default.is_(True),
            )
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_name(self, name: str) -> Project | None:
        stmt = (
            select(self.model)
            .where(self.model.name == name)
            .order_by(desc(self.model.created_at), desc(self.model.id))
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def get_by_external_root_path(self, external_root_path: str) -> Project | None:
        """Find a project by its external storage root."""
        stmt = select(self.model).where(
            self.model.external_root_path == external_root_path
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        workspace_id: str | None = None,
    ) -> tuple[list[Project], Pagination]:
        stmt = select(self.model)
        if workspace_id:
            stmt = stmt.where(self.model.workspace_id == workspace_id)
        stmt = stmt.where(
            or_(self.model.user_id.is_(None), self.model.user_id != "system")
        )
        stmt = self._apply_search(stmt, [self.model.name], search)
        return await super().list(limit=limit, cursor=cursor, stmt=stmt)
