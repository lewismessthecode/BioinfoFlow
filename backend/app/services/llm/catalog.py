from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm import LlmModelProfile, LlmProvider
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderRepository,
)
from app.utils.authorization import ADMIN_ROLES
from app.utils.exceptions import NotFoundError, PermissionDeniedError


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
        workspace_id, user_id = _tenant_fields_for_scope(
            scope=data.get("scope", "user"),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        return await self.provider_repo.create(
            name=data["name"],
            kind=data["kind"],
            base_url=data.get("base_url"),
            api_key_ref=data.get("api_key_ref"),
            scope=data.get("scope", "user"),
            workspace_id=workspace_id,
            user_id=user_id,
            enabled=data.get("enabled", True),
            provider_metadata=data.get("metadata"),
        )

    async def update_provider(self, provider_id: str, data: dict[str, Any]):
        provider = await self._get_writable_provider(
            provider_id,
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        updates = _strip_none(data)
        _drop_request_tenant_fields(updates)
        if "scope" in updates:
            workspace_id, user_id = _tenant_fields_for_scope(
                scope=updates["scope"],
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )
            updates["workspace_id"] = workspace_id
            updates["user_id"] = user_id
        if "metadata" in updates:
            updates["provider_metadata"] = updates.pop("metadata")
        return await self.provider_repo.update_all(provider, **updates)

    async def test_provider(
        self,
        provider_id: str,
        *,
        workspace_id: str,
        user_id: str,
        role: str | None = None,
    ):
        provider = await self._get_writable_provider(
            provider_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )
        status = {
            "success": True,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "mode": "contract_only",
        }
        return await self.provider_repo.update_all(provider, test_status=status)

    async def list_models(
        self,
        provider_id: str | None = None,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ):
        visible_providers = await self.provider_repo.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        visible_provider_ids = {str(provider.id) for provider in visible_providers}
        if provider_id:
            provider = await self.provider_repo.get(provider_id)
            if provider is None:
                raise NotFoundError(f"LLM provider not found: {provider_id}")
            if str(provider.id) not in visible_provider_ids:
                raise PermissionDeniedError("LLM provider is not visible to this user")
            return await self.model_repo.list_for_provider(provider_id)
        return await self.model_repo.list_for_providers(sorted(visible_provider_ids))

    async def create_model(self, data: dict[str, Any]):
        await self._get_writable_provider(
            str(data["provider_id"]),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
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
        await self._get_writable_provider(
            str(model.provider_id),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        updates = _strip_none(data)
        _drop_request_tenant_fields(updates)
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
        workspace_id, user_id = _tenant_fields_for_scope(
            scope=data.get("scope", "user"),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        await self._ensure_models_visible(
            [str(data["primary_model_id"]), *[str(item) for item in data.get("fallback_model_ids") or []]],
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
        )
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
            workspace_id=workspace_id,
            user_id=user_id,
            enabled=data.get("enabled", True),
            profile_metadata=data.get("metadata"),
        )

    async def update_profile(self, profile_id: str, data: dict[str, Any]):
        profile = await self._get_writable_profile(
            profile_id,
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        updates = _strip_none(data)
        _drop_request_tenant_fields(updates)
        if "metadata" in updates:
            updates["profile_metadata"] = updates.pop("metadata")
        if "primary_model_id" in updates:
            await self._ensure_models_visible(
                [str(updates["primary_model_id"])],
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
            )
            updates["primary_model_id"] = str(updates["primary_model_id"])
        if "fallback_model_ids" in updates and updates["fallback_model_ids"] is not None:
            await self._ensure_models_visible(
                [str(item) for item in updates["fallback_model_ids"]],
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
            )
            updates["fallback_model_ids"] = [
                str(item) for item in updates["fallback_model_ids"]
            ]
        if "scope" in updates:
            workspace_id, user_id = _tenant_fields_for_scope(
                scope=updates["scope"],
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )
            updates["workspace_id"] = workspace_id
            updates["user_id"] = user_id
        return await self.profile_repo.update_all(profile, **updates)

    async def _get_writable_provider(
        self,
        provider_id: str,
        *,
        workspace_id: str,
        user_id: str,
        role: str | None = None,
    ) -> LlmProvider:
        provider = await self.provider_repo.get(provider_id)
        if provider is None:
            raise NotFoundError(f"LLM provider not found: {provider_id}")
        if not _can_write_scoped_resource(
            provider,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        ):
            raise PermissionDeniedError("LLM provider is not writable by this user")
        return provider

    async def _get_writable_profile(
        self,
        profile_id: str,
        *,
        workspace_id: str,
        user_id: str,
        role: str | None = None,
    ) -> LlmModelProfile:
        profile = await self.profile_repo.get(profile_id)
        if profile is None:
            raise NotFoundError(f"LLM model profile not found: {profile_id}")
        if not _can_write_scoped_resource(
            profile,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        ):
            raise PermissionDeniedError("LLM model profile is not writable by this user")
        return profile

    async def _ensure_models_visible(
        self,
        model_ids: list[str],
        *,
        workspace_id: str,
        user_id: str,
    ) -> None:
        for model_id in model_ids:
            model = await self.model_repo.get(model_id)
            if model is None:
                raise NotFoundError(f"LLM model not found: {model_id}")
            provider = await self.provider_repo.get(str(model.provider_id))
            if provider is None:
                raise NotFoundError(f"LLM provider not found: {model.provider_id}")
            if not _is_visible_scoped_resource(
                provider,
                workspace_id=workspace_id,
                user_id=user_id,
            ):
                raise PermissionDeniedError("LLM model is not visible to this user")


def _strip_none(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _drop_request_tenant_fields(data: dict[str, Any]) -> None:
    data.pop("workspace_id", None)
    data.pop("user_id", None)
    data.pop("role", None)


def _tenant_fields_for_scope(
    *,
    scope: str,
    workspace_id: str,
    user_id: str,
    role: str | None = None,
) -> tuple[str | None, str | None]:
    if scope == "global":
        _ensure_can_write_shared_scope(scope=scope, role=role)
        return None, None
    if scope == "workspace":
        _ensure_can_write_shared_scope(scope=scope, role=role)
        return str(workspace_id), None
    return str(workspace_id), user_id


def _ensure_can_write_shared_scope(*, scope: str, role: str | None = None) -> None:
    if settings.auth_is_team and scope in {"global", "workspace"} and role not in ADMIN_ROLES:
        raise PermissionDeniedError(
            "Workspace and global LLM catalog entries require owner/admin access"
        )


def _is_visible_scoped_resource(
    resource: LlmProvider | LlmModelProfile,
    *,
    workspace_id: str,
    user_id: str,
) -> bool:
    scope = str(getattr(resource, "scope", "user") or "user")
    resource_workspace_id = (
        str(resource.workspace_id) if getattr(resource, "workspace_id", None) else None
    )
    resource_user_id = getattr(resource, "user_id", None)

    if scope == "global":
        return resource_workspace_id is None and resource_user_id is None
    if scope == "workspace":
        return resource_workspace_id == str(workspace_id) and resource_user_id is None
    return resource_workspace_id == str(workspace_id) and resource_user_id == user_id


def _can_write_scoped_resource(
    resource: LlmProvider | LlmModelProfile,
    *,
    workspace_id: str,
    user_id: str,
    role: str | None = None,
) -> bool:
    if not _is_visible_scoped_resource(
        resource,
        workspace_id=workspace_id,
        user_id=user_id,
    ):
        return False
    scope = str(getattr(resource, "scope", "user") or "user")
    if scope == "user":
        return getattr(resource, "user_id", None) == user_id
    return not settings.auth_is_team or role in ADMIN_ROLES
