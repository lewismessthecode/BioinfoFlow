from __future__ import annotations

from sqlalchemy import desc, select

from app.models.container_registry import ContainerRegistry
from app.repositories.base import BaseRepository


class ContainerRegistryRepository(BaseRepository[ContainerRegistry]):
    model = ContainerRegistry

    async def list_all(self) -> list[ContainerRegistry]:
        stmt = select(self.model).order_by(
            self.model.name,
            self.model.endpoint,
            self.model.id,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_by_endpoint(self, endpoint: str) -> ContainerRegistry | None:
        stmt = (
            select(self.model)
            .where(self.model.endpoint == endpoint)
            .order_by(desc(self.model.updated_at), desc(self.model.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
