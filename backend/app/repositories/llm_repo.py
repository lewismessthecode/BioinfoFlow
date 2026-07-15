from __future__ import annotations

from sqlalchemy import and_, desc, or_, select

from app.models.llm import (
    LlmModel,
    LlmModelProfile,
    LlmProvider,
    LlmProviderCredential,
)
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

    async def get_visible(
        self,
        provider_id: str,
        *,
        workspace_id: str,
        user_id: str,
        enabled_only: bool = False,
    ) -> LlmProvider | None:
        stmt = select(self.model).where(
            self.model.id == provider_id,
            _visible_provider_clause(self.model, workspace_id=workspace_id, user_id=user_id),
        )
        if enabled_only:
            stmt = stmt.where(self.model.enabled.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


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

    async def get_by_provider_model(
        self,
        *,
        provider_id: str,
        model_id: str,
    ) -> LlmModel | None:
        stmt = select(self.model).where(
            self.model.provider_id == provider_id,
            self.model.model_id == model_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def get_visible(
        self,
        model_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ) -> LlmModel | None:
        stmt = (
            select(self.model)
            .join(LlmProvider, self.model.provider_id == LlmProvider.id)
            .where(
                self.model.id == model_id,
                LlmProvider.enabled.is_(True),
                _visible_provider_clause(
                    LlmProvider,
                    workspace_id=workspace_id,
                    user_id=user_id,
                ),
            )
        )
        result = await self.session.execute(stmt)
        model = result.scalar_one_or_none()
        if model is not None and not _model_is_active(model):
            return None
        return model

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

    async def get_visible(
        self,
        profile_id: str,
        *,
        workspace_id: str,
        user_id: str,
        enabled_only: bool = False,
    ) -> LlmModelProfile | None:
        stmt = select(self.model).where(
            self.model.id == profile_id,
            _visible_provider_clause(self.model, workspace_id=workspace_id, user_id=user_id),
        )
        if enabled_only:
            stmt = stmt.where(self.model.enabled.is_(True))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


class LlmProviderCredentialRepository(BaseRepository[LlmProviderCredential]):
    model = LlmProviderCredential

    async def get_for_provider(
        self,
        provider_id: str,
    ) -> LlmProviderCredential | None:
        stmt = select(self.model).where(self.model.provider_id == provider_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()


def _visible_provider_clause(resource, *, workspace_id: str, user_id: str):
    return or_(
        and_(
            resource.scope == "global",
            resource.workspace_id.is_(None),
            resource.user_id.is_(None),
        ),
        and_(
            resource.scope == "workspace",
            resource.workspace_id == workspace_id,
            resource.user_id.is_(None),
        ),
        and_(
            resource.scope == "user",
            resource.workspace_id == workspace_id,
            resource.user_id == user_id,
        ),
    )


def _model_is_active(model: LlmModel) -> bool:
    metadata = getattr(model, "model_metadata", None) or {}
    return metadata.get("catalog_status") != "stale"
