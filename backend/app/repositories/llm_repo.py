from __future__ import annotations

from sqlalchemy import desc, select

from app.models.llm import LlmModel, LlmModelProfile, LlmProvider
from app.repositories.base import BaseRepository


class LlmProviderRepository(BaseRepository[LlmProvider]):
    model = LlmProvider

    async def list_available(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        enabled_only: bool = False,
    ) -> list[LlmProvider]:
        stmt = select(self.model)
        if enabled_only:
            stmt = stmt.where(self.model.enabled.is_(True))
        if workspace_id:
            stmt = stmt.where(
                (self.model.workspace_id == workspace_id)
                | (self.model.workspace_id.is_(None))
            )
        if user_id:
            stmt = stmt.where(
                (self.model.user_id == user_id) | (self.model.user_id.is_(None))
            )
        stmt = stmt.order_by(desc(self.model.updated_at), desc(self.model.id))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class LlmModelRepository(BaseRepository[LlmModel]):
    model = LlmModel

    async def list_for_provider(self, provider_id: str) -> list[LlmModel]:
        stmt = (
            select(self.model)
            .where(self.model.provider_id == provider_id)
            .order_by(self.model.display_name, self.model.model_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_for_providers(self, provider_ids: list[str]) -> list[LlmModel]:
        if not provider_ids:
            return []
        stmt = (
            select(self.model)
            .where(self.model.provider_id.in_(provider_ids))
            .order_by(self.model.display_name, self.model.model_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class LlmModelProfileRepository(BaseRepository[LlmModelProfile]):
    model = LlmModelProfile

    async def list_available(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
        enabled_only: bool = False,
    ) -> list[LlmModelProfile]:
        stmt = select(self.model)
        if enabled_only:
            stmt = stmt.where(self.model.enabled.is_(True))
        if workspace_id:
            stmt = stmt.where(
                (self.model.workspace_id == workspace_id)
                | (self.model.workspace_id.is_(None))
            )
        if user_id:
            stmt = stmt.where(
                (self.model.user_id == user_id) | (self.model.user_id.is_(None))
            )
        stmt = stmt.order_by(self.model.task_type, self.model.name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
