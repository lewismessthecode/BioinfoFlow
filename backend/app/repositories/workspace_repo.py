from __future__ import annotations

from sqlalchemy import select

from app.models.workspace import Workspace, WorkspaceMembership
from app.repositories.base import BaseRepository


class WorkspaceRepository(BaseRepository[Workspace]):
    model = Workspace

    async def get_default(self, workspace_id: str) -> Workspace | None:
        stmt = select(self.model).where(self.model.id == workspace_id).limit(1)
        result = await self.session.execute(stmt)
        return result.scalars().first()


class WorkspaceMembershipRepository(BaseRepository[WorkspaceMembership]):
    model = WorkspaceMembership

    async def get_for_user(
        self, *, workspace_id: str, user_id: str
    ) -> WorkspaceMembership | None:
        stmt = select(self.model).where(
            self.model.workspace_id == workspace_id,
            self.model.user_id == user_id,
        )
        result = await self.session.execute(stmt.limit(1))
        return result.scalars().first()
