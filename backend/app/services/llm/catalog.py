from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderRepository,
)
from app.utils.exceptions import NotFoundError


class LlmCatalogService:
    def __init__(self, session: AsyncSession):
        self.provider_repo = LlmProviderRepository(session)
        self.model_repo = LlmModelRepository(session)
        self.profile_repo = LlmModelProfileRepository(session)

    async def list_providers(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ):
        return await self.provider_repo.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def create_provider(self, data: dict[str, Any]):
        return await self.provider_repo.create(
            name=data["name"],
            kind=data["kind"],
            base_url=data.get("base_url"),
            api_key_ref=data.get("api_key_ref"),
            scope=data.get("scope", "user"),
            workspace_id=str(data["workspace_id"]) if data.get("workspace_id") else None,
            user_id=data.get("user_id"),
            enabled=data.get("enabled", True),
            provider_metadata=data.get("metadata"),
        )

    async def update_provider(self, provider_id: str, data: dict[str, Any]):
        provider = await self.provider_repo.get(provider_id)
        if provider is None:
            raise NotFoundError(f"LLM provider not found: {provider_id}")
        updates = _strip_none(data)
        if "metadata" in updates:
            updates["provider_metadata"] = updates.pop("metadata")
        if "workspace_id" in updates and updates["workspace_id"] is not None:
            updates["workspace_id"] = str(updates["workspace_id"])
        return await self.provider_repo.update_all(provider, **updates)

    async def test_provider(self, provider_id: str):
        provider = await self.provider_repo.get(provider_id)
        if provider is None:
            raise NotFoundError(f"LLM provider not found: {provider_id}")
        status = {
            "success": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": "contract_only",
        }
        return await self.provider_repo.update_all(provider, test_status=status)

    async def list_models(self, provider_id: str | None = None):
        if provider_id:
            return await self.model_repo.list_for_provider(provider_id)
        items, _pagination = await self.model_repo.list(limit=200)
        return items

    async def create_model(self, data: dict[str, Any]):
        return await self.model_repo.create(
            provider_id=str(data["provider_id"]),
            model_id=data["model_id"],
            display_name=data["display_name"],
            context_length=data.get("context_length"),
            max_output_tokens=data.get("max_output_tokens"),
            supports_tools=data.get("supports_tools", False),
            supports_streaming=data.get("supports_streaming", True),
            supports_vision=data.get("supports_vision", False),
            supports_json_schema=data.get("supports_json_schema", False),
            supports_reasoning=data.get("supports_reasoning", False),
            default_temperature=data.get("default_temperature"),
            default_top_p=data.get("default_top_p"),
            cost_metadata=data.get("cost_metadata"),
            model_metadata=data.get("metadata"),
        )

    async def update_model(self, model_id: str, data: dict[str, Any]):
        model = await self.model_repo.get(model_id)
        if model is None:
            raise NotFoundError(f"LLM model not found: {model_id}")
        updates = _strip_none(data)
        if "metadata" in updates:
            updates["model_metadata"] = updates.pop("metadata")
        return await self.model_repo.update_all(model, **updates)

    async def list_profiles(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ):
        return await self.profile_repo.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
        )

    async def create_profile(self, data: dict[str, Any]):
        fallback_ids = data.get("fallback_model_ids")
        return await self.profile_repo.create(
            name=data["name"],
            task_type=data["task_type"],
            primary_model_id=str(data["primary_model_id"]),
            fallback_model_ids=[str(item) for item in fallback_ids] if fallback_ids else None,
            reasoning_budget=data.get("reasoning_budget"),
            max_tokens=data.get("max_tokens"),
            cost_ceiling=data.get("cost_ceiling"),
            routing_policy=data.get("routing_policy"),
            permission_overrides=data.get("permission_overrides"),
            scope=data.get("scope", "user"),
            workspace_id=str(data["workspace_id"]) if data.get("workspace_id") else None,
            user_id=data.get("user_id"),
            enabled=data.get("enabled", True),
            profile_metadata=data.get("metadata"),
        )

    async def update_profile(self, profile_id: str, data: dict[str, Any]):
        profile = await self.profile_repo.get(profile_id)
        if profile is None:
            raise NotFoundError(f"LLM model profile not found: {profile_id}")
        updates = _strip_none(data)
        if "metadata" in updates:
            updates["profile_metadata"] = updates.pop("metadata")
        if "primary_model_id" in updates:
            updates["primary_model_id"] = str(updates["primary_model_id"])
        if "fallback_model_ids" in updates and updates["fallback_model_ids"] is not None:
            updates["fallback_model_ids"] = [
                str(item) for item in updates["fallback_model_ids"]
            ]
        if "workspace_id" in updates and updates["workspace_id"] is not None:
            updates["workspace_id"] = str(updates["workspace_id"])
        return await self.profile_repo.update_all(profile, **updates)


def _strip_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}
