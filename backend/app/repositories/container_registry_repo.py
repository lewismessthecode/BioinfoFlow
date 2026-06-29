from __future__ import annotations

from sqlalchemy import desc, select, update

from app.models.container_registry import ContainerRegistry
from app.repositories.base import BaseRepository


class ContainerRegistryRepository(BaseRepository[ContainerRegistry]):
    model = ContainerRegistry

    async def list_all(self) -> list[ContainerRegistry]:
        stmt = select(self.model).order_by(
            desc(self.model.is_default),
            self.model.name,
            self.model.endpoint,
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_default(self) -> ContainerRegistry | None:
        stmt = (
            select(self.model)
            .where(self.model.is_default.is_(True))
            .order_by(desc(self.model.updated_at), desc(self.model.id))
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def unset_default_except(self, registry_id: str | None = None) -> None:
        stmt = update(self.model).where(self.model.is_default.is_(True))
        if registry_id:
            stmt = stmt.where(self.model.id != registry_id)
        await self.session.execute(stmt.values(is_default=False))
        await self.session.commit()
