from __future__ import annotations

from typing import Iterable

from sqlalchemy import select

from app.models.image import DockerImage
from app.repositories.base import BaseRepository
from app.schemas.common import Pagination


class ImageRepository(BaseRepository[DockerImage]):
    model = DockerImage

    async def list(
        self,
        *,
        limit: int = 20,
        cursor: str | None = None,
        search: str | None = None,
        status: str | None = None,
    ) -> tuple[list[DockerImage], Pagination]:
        stmt = select(self.model)
        stmt = self._apply_search(stmt, [self.model.name, self.model.full_name], search)
        filters = {"status": status}
        return await super().list(
            limit=limit, cursor=cursor, filters=filters, stmt=stmt
        )

    async def get_by_full_name(self, full_name: str) -> DockerImage | None:
        stmt = select(self.model).where(self.model.full_name == full_name)
        result = await self.session.execute(stmt)
        return result.scalars().first()

    async def list_by_statuses(self, statuses: Iterable[str]) -> list[DockerImage]:
        stmt = select(self.model).where(self.model.status.in_(list(statuses)))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_not_in_full_names(
        self,
        full_names: Iterable[str],
        *,
        statuses: Iterable[str] | None = None,
    ) -> list[DockerImage]:
        stmt = select(self.model)
        if statuses:
            stmt = stmt.where(self.model.status.in_(list(statuses)))
        names = list(full_names)
        if names:
            stmt = stmt.where(self.model.full_name.notin_(names))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
