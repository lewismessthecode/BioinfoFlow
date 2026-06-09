from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
from typing import Any
from urllib.parse import urlparse

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm import LlmCredentialSource, LlmModelProfile, LlmProvider
from app.repositories.llm_repo import (
    LlmModelProfileRepository,
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.services.llm.credentials import (
    credential_available,
    credential_configured,
    encrypt_secret,
    fingerprint_secret,
    mask_secret,
    to_credential_read_dict,
)
from app.services.llm.providers import normalize_ollama_base_url
from app.utils.authorization import ADMIN_ROLES
from app.utils.exceptions import NotFoundError, PermissionDeniedError


class LlmCatalogService:
    def __init__(self, session: AsyncSession):
        self.provider_repo = LlmProviderRepository(session)
        self.model_repo = LlmModelRepository(session)
        self.profile_repo = LlmModelProfileRepository(session)
        self.credential_repo = LlmProviderCredentialRepository(session)

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
        _validate_provider_base_url(data.get("base_url"))
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
        if "base_url" in updates:
            _validate_provider_base_url(updates.get("base_url"))
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

    async def upsert_provider_credential(
        self,
        provider_id: str,
        data: dict[str, Any],
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
        source = str(data.get("source") or LlmCredentialSource.NONE)
        existing = await self.credential_repo.get_for_provider(str(provider.id))

        if source == LlmCredentialSource.ENV:
            env_var_name = str(data.get("env_var_name") or "").strip()
            if not env_var_name:
                raise ValueError("Environment variable name is required")
            payload = {
                "source": source,
                "env_var_name": env_var_name,
                "encrypted_secret": None,
                "fingerprint": None,
                "masked_hint": f"env:{env_var_name}",
                "updated_by": user_id,
            }
        elif source == LlmCredentialSource.STORED:
            secret = str(data.get("secret") or "").strip()
            if not secret:
                raise ValueError("Secret is required")
            payload = {
                "source": source,
                "env_var_name": None,
                "encrypted_secret": encrypt_secret(secret),
                "fingerprint": fingerprint_secret(secret),
                "masked_hint": mask_secret(secret),
                "updated_by": user_id,
            }
        else:
            payload = {
                "source": LlmCredentialSource.NONE,
                "env_var_name": None,
                "encrypted_secret": None,
                "fingerprint": None,
                "masked_hint": None,
                "updated_by": user_id,
            }

        if existing:
            credential = await self.credential_repo.update_all(existing, **payload)
        else:
            credential = await self.credential_repo.create(
                provider_id=str(provider.id),
                **payload,
            )
        return provider, credential

    async def get_provider_credential(
        self,
        provider_id: str,
        *,
        workspace_id: str,
        user_id: str,
    ):
        provider = await self.provider_repo.get(provider_id)
        if provider is None:
            raise NotFoundError(f"LLM provider not found: {provider_id}")
        if not _is_visible_scoped_resource(
            provider,
            workspace_id=workspace_id,
            user_id=user_id,
        ):
            raise PermissionDeniedError("LLM provider is not visible to this user")
        return await self.credential_repo.get_for_provider(str(provider.id))

    def credential_read_dict(self, provider: LlmProvider, credential) -> dict[str, Any]:
        return to_credential_read_dict(
            provider_id=str(provider.id),
            credential=credential,
            credential_required=_provider_requires_credential(provider),
        )

    async def configuration(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        providers = await self.list_providers(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        provider_ids = [str(provider.id) for provider in providers]
        models = await self.model_repo.list_for_providers(provider_ids)
        profiles = await self.list_profiles(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        credentials = {
            str(provider.id): await self.credential_repo.get_for_provider(str(provider.id))
            for provider in providers
        }
        provider_payloads = []
        for provider in providers:
            credential = credentials.get(str(provider.id))
            provider_payloads.append(
                {
                    "provider": provider,
                    "credential": self.credential_read_dict(provider, credential),
                }
            )
        return {
            "providers": provider_payloads,
            "models": models,
            "profiles": profiles,
            "summary": {
                "provider_count": len(providers),
                "configured_provider_count": sum(
                    1
                    for credential in credentials.values()
                    if credential_configured(credential)
                ),
                "available_provider_count": sum(
                    1
                    for provider in providers
                    if credential_available(
                        credentials.get(str(provider.id)),
                        credential_required=_provider_requires_credential(provider),
                    )
                ),
                "model_count": len(models),
                "profile_count": len(profiles),
            },
        }

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

    async def discover_models(
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
        if provider.kind != "ollama":
            raise ValueError("Model discovery is currently supported for Ollama only")
        base_url = normalize_ollama_base_url(
            provider.base_url or settings.ollama_base_url
        )
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base_url}/api/tags")
            response.raise_for_status()
        models = []
        for item in _ollama_models_from_tags(response.json()):
            existing = await self.model_repo.get_by_provider_model(
                provider_id=str(provider.id),
                model_id=item["model_id"],
            )
            values = {
                "display_name": item["display_name"],
                "context_length": item["context_length"],
                "max_output_tokens": item["max_output_tokens"],
                "supports_tools": False,
                "supports_streaming": True,
                "supports_vision": False,
                "supports_json_schema": False,
                "supports_reasoning": item["supports_reasoning"],
                "model_metadata": item["metadata"],
            }
            if existing:
                model = await self.model_repo.update_all(existing, **values)
            else:
                model = await self.model_repo.create(
                    provider_id=str(provider.id),
                    model_id=item["model_id"],
                    default_temperature=None,
                    default_top_p=None,
                    cost_metadata=None,
                    **values,
                )
            models.append(model)
        return models

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
            prefer_streaming=data.get("prefer_streaming", True),
            allow_thinking=data.get("allow_thinking", True),
            allow_tools=data.get("allow_tools", True),
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


def _provider_requires_credential(provider: LlmProvider) -> bool:
    metadata = provider.provider_metadata or {}
    if metadata.get("authMode") == "none":
        return False
    return provider.kind != "ollama"


def _drop_request_tenant_fields(data: dict[str, Any]) -> None:
    data.pop("workspace_id", None)
    data.pop("user_id", None)
    data.pop("role", None)


def _validate_provider_base_url(base_url: str | None) -> None:
    if not base_url:
        return
    parsed = urlparse(str(base_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provider endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "https":
        return
    host = parsed.hostname or ""
    if host in {"localhost", "127.0.0.1", "::1"}:
        return
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local:
            return
    except ValueError:
        pass
    raise ValueError("Public provider endpoints must use HTTPS")


def _ollama_models_from_tags(payload: Any) -> list[dict[str, Any]]:
    raw_models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        model_id = str(item.get("model") or item.get("name") or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        details = item.get("details") if isinstance(item.get("details"), dict) else {}
        models.append(
            {
                "model_id": model_id,
                "display_name": _display_name_for_ollama_model(model_id),
                "context_length": None,
                "max_output_tokens": None,
                "supports_reasoning": _ollama_model_supports_reasoning(model_id),
                "metadata": {
                    "source": "ollama_discovery",
                    "parameter_size": details.get("parameter_size"),
                    "family": details.get("family"),
                    "families": details.get("families"),
                },
            }
        )
    return models


def _display_name_for_ollama_model(model_id: str) -> str:
    base = model_id.split(":", 1)[0]
    replacements = {
        "deepseek-r1": "DeepSeek R1",
        "llama3.3": "Llama 3.3",
    }
    if base in replacements:
        return replacements[base]
    return " ".join(part.capitalize() for part in base.replace("-", " ").split())


def _ollama_model_supports_reasoning(model_id: str) -> bool:
    normalized = model_id.lower()
    return "deepseek-r1" in normalized or "reason" in normalized


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
