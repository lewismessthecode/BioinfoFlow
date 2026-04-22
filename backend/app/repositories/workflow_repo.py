from __future__ import annotations

from sqlalchemy import select

from app.models.workflow import Workflow
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class WorkflowRepository(BaseRepository[Workflow]):
    model = Workflow

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        source: str | None = None,
    ) -> tuple[list[Workflow], Pagination]:
        stmt = select(self.model)
        stmt = self._apply_search(
            stmt, [self.model.name, self.model.description], search
        )
        filters = {"source": source}
        return await super().list(
            limit=limit, cursor=cursor, filters=filters, stmt=stmt
        )

    async def get_by_unique(
        self, *, source: str, name: str, version: str
    ) -> Workflow | None:
        stmt = select(self.model).where(
            self.model.source == source,
            self.model.name == name,
            self.model.version == version,
        )
        result = await self.session.execute(stmt)
        return result.scalars().first()
