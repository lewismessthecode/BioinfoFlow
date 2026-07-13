from __future__ import annotations

from datetime import datetime, timezone
import ipaddress
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.llm import LlmCredentialSource, LlmModelProfile, LlmProvider
from app.schemas.llm import LlmProviderUpdate
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
    generate_credential_fingerprint,
    mask_secret,
    resolve_credential_material,
    to_credential_read_dict,
)
from app.services.llm.access_policy import (
    authorize_provider_endpoint,
    authorize_server_environment_credential,
    resolve_provider_network_access,
)
from app.services.llm.provider_templates import (
    ModelTemplate,
    ProviderTemplate,
    get_provider_template,
    list_provider_templates,
    normalize_ollama_base_url,
    normalize_openai_compatible_base_url,
    normalize_provider_base_url,
    provider_template_for_provider,
    validate_provider_configuration,
)
from app.services.llm.probe import LlmProviderProbe
from app.services.model_runtime.backend.litellm_network import (
    network_policy_http_client,
)
from app.services.model_runtime.contracts import NetworkAccessPolicy
from app.services.llm.test_status import (
    attach_provider_test_fingerprint,
    compute_provider_test_fingerprint,
    is_provider_test_status_current,
    sanitize_provider_test_status,
)
from app.utils.authorization import ADMIN_ROLES, can_manage_server_integrations
from app.utils.exceptions import NotFoundError, PermissionDeniedError


class LlmCatalogService:
    def __init__(self, session: AsyncSession):
        self.provider_repo = LlmProviderRepository(session)
        self.model_repo = LlmModelRepository(session)
        self.profile_repo = LlmModelProfileRepository(session)
        self.credential_repo = LlmProviderCredentialRepository(session)
        self.probe = LlmProviderProbe()

    async def list_providers(
        self,
        *,
        workspace_id: str | None = None,
        user_id: str | None = None,
    ):
        providers = await self.provider_repo.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        return [await self._refresh_provider_test_status(provider) for provider in providers]

    async def create_provider(self, data: dict[str, Any]):
        kind, wire_protocol = validate_provider_configuration(
            str(data["kind"]),
            str(data.get("wire_protocol", "chat_completions")),
        )
        _validate_provider_base_url(
            data.get("base_url"),
            allow_insecure_http=bool(data.get("allow_insecure_http", False)),
        )
        await authorize_provider_endpoint(
            data.get("base_url"),
            role=data.get("role"),
        )
        workspace_id, user_id = _tenant_fields_for_scope(
            scope=data.get("scope", "user"),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        return await self.provider_repo.create(
            name=data["name"],
            kind=kind,
            wire_protocol=wire_protocol,
            base_url=data.get("base_url"),
            api_key_ref=data.get("api_key_ref"),
            scope=data.get("scope", "user"),
            workspace_id=workspace_id,
            user_id=user_id,
            enabled=data.get("enabled", True),
            allow_insecure_http=bool(data.get("allow_insecure_http", False)),
            provider_metadata=data.get("metadata"),
        )

    async def _refresh_provider_test_status(
        self,
        provider: LlmProvider,
    ) -> LlmProvider:
        status = sanitize_provider_test_status(provider.test_status)
        if status is None:
            return provider
        models = await self.model_repo.list_for_provider(str(provider.id))
        no_model_status = status.get("error_code") == "model_not_configured"
        tested_model_id = status.get("model") or status.get("model_id")
        tested_model = (
            None
            if no_model_status
            else next(
                (
                    model
                    for model in models
                    if isinstance(tested_model_id, str)
                    and model.model_id == tested_model_id
                ),
                None,
            )
        )
        credential = await self.credential_repo.get_for_provider(str(provider.id))
        if (no_model_status and models) or (
            not no_model_status and tested_model is None
        ) or not is_provider_test_status_current(
            provider.test_status,
            provider=provider,
            credential=credential,
            tested_model=tested_model,
        ):
            return await self.provider_repo.update_all(provider, test_status=None)
        return provider

    def list_provider_templates(self) -> list[ProviderTemplate]:
        return list_provider_templates()

    async def setup_provider(self, data: dict[str, Any]) -> dict[str, Any]:
        template_id = str(data.get("template_id") or "").strip()
        template = get_provider_template(template_id)
        if template is None:
            raise ValueError(f"Unknown LLM provider template: {template_id}")

        provider = await self._provider_for_setup(template=template, data=data)
        allow_insecure_http = bool(
            data.get(
                "allow_insecure_http",
                provider.allow_insecure_http if provider is not None else False,
            )
        )
        base_url = data.get("base_url")
        if base_url:
            base_url = normalize_provider_base_url(template.kind, str(base_url))
            _validate_provider_base_url(
                base_url,
                allow_insecure_http=allow_insecure_http,
            )
        elif template.default_base_url:
            base_url = normalize_provider_base_url(template.kind, template.default_base_url)

        metadata = {
            **(provider.provider_metadata if provider is not None else {}),
            "providerTemplate": template.id,
        }
        if provider is None:
            provider = await self.create_provider(
                {
                    **data,
                    "name": str(data.get("name") or template.name),
                    "kind": template.kind,
                    "base_url": base_url,
                    "api_key_ref": None,
                    "allow_insecure_http": allow_insecure_http,
                    "metadata": metadata,
                }
            )
        else:
            provider = await self.update_provider(
                str(provider.id),
                {
                    "workspace_id": data["workspace_id"],
                    "user_id": data["user_id"],
                    "role": data.get("role"),
                    "name": str(data.get("name") or provider.name or template.name),
                    "kind": template.kind,
                    "wire_protocol": data.get(
                        "wire_protocol",
                        provider.wire_protocol,
                    ),
                    "base_url": base_url,
                    "allow_insecure_http": allow_insecure_http,
                    "metadata": metadata,
                    "enabled": data.get("enabled", True),
                },
            )

        secret = str(data.get("api_key") or "").strip()
        existing_credential = await self.credential_repo.get_for_provider(str(provider.id))
        if secret:
            provider, credential = await self.upsert_provider_credential(
                str(provider.id),
                {"source": LlmCredentialSource.STORED, "secret": secret},
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )
        elif existing_credential is None and not template.api_key_required:
            provider, credential = await self.upsert_provider_credential(
                str(provider.id),
                {"source": LlmCredentialSource.NONE},
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )
        else:
            credential = existing_credential

        models: list[Any] = []
        for model_id in _clean_model_ids(data.get("model_ids")):
            models.append(await self._upsert_model_from_template_id(provider, model_id))
        if not models and template.models:
            for model_template in template.models:
                models.append(await self._upsert_model_from_template(provider, model_template))
        discovered = False
        if data.get("discover"):
            models = await self.discover_models(
                str(provider.id),
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )
            discovered = True

        return {
            "provider": provider,
            "credential": self.credential_read_dict(provider, credential),
            "models": models,
            "discovered": discovered,
        }

    async def update_provider(self, provider_id: str, data: dict[str, Any]):
        provider = await self._get_writable_provider(
            provider_id,
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        requested_update = LlmProviderUpdate.model_validate(data)
        requested_update.validate_merged_wire_protocol(
            current_kind=provider.kind,
            current_wire_protocol=provider.wire_protocol,
        )
        updates = _strip_none(data)
        _drop_request_tenant_fields(updates)
        _validate_provider_base_url(
            updates.get("base_url", provider.base_url),
            allow_insecure_http=bool(
                updates.get("allow_insecure_http", provider.allow_insecure_http)
            ),
        )
        await authorize_provider_endpoint(
            updates.get("base_url", provider.base_url),
            role=data.get("role"),
        )
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
            next_metadata = updates.pop("metadata")
            updates["provider_metadata"] = next_metadata
        provider = await self.provider_repo.update_all(provider, **updates)
        return await self._refresh_provider_test_status(provider)

    async def test_provider(
        self,
        provider_id: str,
        *,
        model_id: str | None = None,
        workspace_id: str,
        user_id: str,
        role: str | None = None,
    ) -> dict[str, Any]:
        provider = await self._get_writable_provider(
            provider_id,
            workspace_id=workspace_id,
            user_id=user_id,
            role=role,
        )
        models = await self.model_repo.list_for_provider(str(provider.id))
        if model_id is not None:
            model = await self.model_repo.get(model_id)
            if model is None or str(model.provider_id) != str(provider.id):
                raise ValueError("The selected model does not belong to this provider")
        else:
            model = models[0] if models else None
        if model is None:
            status = {
                "success": False,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "wire_protocol": provider.wire_protocol,
                "model": None,
                "latency_ms": None,
                "error_code": "model_not_configured",
                "error": "No model is configured for this provider.",
                "retryable": False,
                "http_status": None,
                "provider_code": None,
                "mode": "live_probe",
            }
            credential = await self.credential_repo.get_for_provider(str(provider.id))
            fingerprint = compute_provider_test_fingerprint(provider, credential, None)
            internal_status = attach_provider_test_fingerprint(status, fingerprint)
            await self.provider_repo.update_all(provider, test_status=internal_status)
            return sanitize_provider_test_status(internal_status) or {}

        credential = await self.credential_repo.get_for_provider(str(provider.id))
        probe_base_url = normalize_provider_base_url(provider.kind, provider.base_url)
        network_access = await resolve_provider_network_access(
            probe_base_url,
            private_endpoint_authorized=can_manage_server_integrations(role),
            resolve_dns=not can_manage_server_integrations(role),
        )
        if credential is not None and credential.source == LlmCredentialSource.ENV:
            authorize_server_environment_credential(role=role)
        result = await self.probe.probe(
            endpoint_id=str(provider.id),
            provider_kind=provider.kind,
            model_id=model.model_id,
            wire_protocol=provider.wire_protocol,
            base_url=probe_base_url,
            network_access=network_access,
            credential=resolve_credential_material(credential),
            credential_required=_provider_requires_credential(provider),
        )
        public_result = result.to_public_dict()
        status = {
            **public_result,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "model": public_result.get("model_id") or model.model_id,
            "error": public_result.get("error_message"),
            "mode": "live_probe",
        }
        fingerprint = compute_provider_test_fingerprint(provider, credential, model)
        internal_status = attach_provider_test_fingerprint(status, fingerprint)
        await self.provider_repo.update_all(provider, test_status=internal_status)
        return sanitize_provider_test_status(internal_status) or {}

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
            authorize_server_environment_credential(role=role)
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
                "fingerprint": generate_credential_fingerprint(),
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
        if provider.test_status is not None:
            provider = await self.provider_repo.update_all(provider, test_status=None)
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
        network_access = await resolve_provider_network_access(
            _provider_discovery_base_url(provider),
            private_endpoint_authorized=can_manage_server_integrations(role),
            resolve_dns=not can_manage_server_integrations(role),
        )
        credential = await self.credential_repo.get_for_provider(str(provider.id))
        if credential is not None and credential.source == LlmCredentialSource.ENV:
            authorize_server_environment_credential(role=role)
        return await self.discover_models_unchecked(
            provider,
            network_access=network_access,
        )

    async def discover_models_unchecked(
        self,
        provider: LlmProvider,
        *,
        timeout: float = 10.0,
        network_access: NetworkAccessPolicy,
    ):
        """Discover and upsert models without permission checks.

        Used by the permission-checked ``discover_models`` and by environment
        bootstrap (best-effort). Performs a live network call per provider
        discovery mode and falls back to any static template models. ``timeout``
        bounds each network call so startup bootstrap can fail fast.
        """
        validate_provider_transport(provider)
        template = provider_template_for_provider(provider)
        discovery = template.discovery if template else "openai_models"
        if discovery == "ollama_tags":
            base_url = normalize_ollama_base_url(
                provider.base_url or settings.ollama_base_url
            )
            async with network_policy_http_client(
                network_access=network_access,
                timeout=timeout,
            ) as client:
                response = await client.get(f"{base_url}/api/tags")
                response.raise_for_status()
            return [
                await self._upsert_model_from_discovered(provider, item)
                for item in _ollama_models_from_tags(response.json())
            ]
        if discovery == "anthropic_models":
            base_url = (
                provider.base_url
                or (template.default_base_url if template else None)
                or "https://api.anthropic.com"
            ).rstrip("/")
            material = await self._provider_credential_material(provider)
            if not material.api_key:
                raise ValueError("Anthropic API key is required for model discovery")
            headers = {
                "x-api-key": material.api_key,
                "anthropic-version": "2023-06-01",
            }
            async with network_policy_http_client(
                network_access=network_access,
                timeout=timeout,
            ) as client:
                response = await client.get(
                    f"{base_url}/v1/models",
                    headers=headers,
                    params={"limit": 1000},
                )
                response.raise_for_status()
            return [
                await self._upsert_model_from_discovered(provider, item)
                for item in _anthropic_models_from_list(response.json())
            ]
        if discovery == "gemini_models":
            base_url = (
                provider.base_url
                or (template.default_base_url if template else None)
                or "https://generativelanguage.googleapis.com"
            ).rstrip("/")
            material = await self._provider_credential_material(provider)
            if not material.api_key:
                raise ValueError("Gemini API key is required for model discovery")
            async with network_policy_http_client(
                network_access=network_access,
                timeout=timeout,
            ) as client:
                response = await client.get(
                    f"{base_url}/v1beta/models",
                    headers={"x-goog-api-key": material.api_key},
                    params={"pageSize": 1000},
                )
                response.raise_for_status()
            return [
                await self._upsert_model_from_discovered(provider, item)
                for item in _gemini_models_from_list(response.json())
            ]
        if discovery == "openai_models":
            discovery_base_url = provider.base_url
            if not discovery_base_url and template:
                discovery_base_url = template.default_base_url
            base_url = normalize_openai_compatible_base_url(
                discovery_base_url or "",
                prefer_loopback_ip=provider.kind == "vllm",
            )
            if not base_url:
                raise ValueError("Provider endpoint is required for model discovery")
            material = await self._provider_credential_material(provider)
            headers = (
                {"Authorization": f"Bearer {material.api_key}"}
                if material.api_key
                else None
            )
            async with network_policy_http_client(
                network_access=network_access,
                timeout=timeout,
            ) as client:
                response = await client.get(f"{base_url}/models", headers=headers)
                response.raise_for_status()
            return [
                await self._upsert_model_from_discovered(provider, item)
                for item in _openai_models_from_list(response.json())
            ]
        if template and template.models:
            return [
                await self._upsert_model_from_template(provider, model)
                for model in template.models
            ]
        return []

    async def _provider_credential_material(self, provider: LlmProvider):
        credential = await self.credential_repo.get_for_provider(str(provider.id))
        return resolve_credential_material(credential)

    async def create_model(self, data: dict[str, Any]):
        provider = await self._get_writable_provider(
            str(data["provider_id"]),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        model = await self.model_repo.create(
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
        if provider.test_status is not None:
            await self.provider_repo.update_all(provider, test_status=None)
        return model

    async def _provider_for_setup(
        self,
        *,
        template: ProviderTemplate,
        data: dict[str, Any],
    ) -> LlmProvider | None:
        provider_id = str(data.get("provider_id") or "").strip()
        if provider_id:
            return await self._get_writable_provider(
                provider_id,
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            )

        target_workspace_id, target_user_id = _tenant_fields_for_scope(
            scope=data.get("scope", "user"),
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
            role=data.get("role"),
        )
        providers = await self.list_providers(
            workspace_id=data["workspace_id"],
            user_id=data["user_id"],
        )
        for provider in providers:
            metadata = provider.provider_metadata or {}
            if metadata.get("providerTemplate") != template.id:
                continue
            if provider.scope != data.get("scope", "user"):
                continue
            provider_workspace_id = str(provider.workspace_id) if provider.workspace_id else None
            if provider_workspace_id != target_workspace_id:
                continue
            if provider.user_id != target_user_id:
                continue
            if _can_write_scoped_resource(
                provider,
                workspace_id=data["workspace_id"],
                user_id=data["user_id"],
                role=data.get("role"),
            ):
                return provider
        return None

    async def _upsert_model_from_template_id(self, provider: LlmProvider, model_id: str):
        return await self._upsert_model_from_discovered(
            provider,
            {
                "model_id": model_id,
                "display_name": model_id,
                "context_length": None,
                "max_output_tokens": None,
                "supports_tools": True,
                "supports_streaming": True,
                "supports_vision": False,
                "supports_json_schema": True,
                "supports_reasoning": _model_id_suggests_reasoning(model_id),
                "metadata": {"source": "manual"},
            },
        )

    async def _upsert_model_from_template(
        self,
        provider: LlmProvider,
        model_template: ModelTemplate,
    ):
        return await self._upsert_model_from_discovered(
            provider,
            {
                "model_id": model_template.id,
                "display_name": model_template.name,
                "context_length": model_template.context_length,
                "max_output_tokens": model_template.max_output_tokens,
                "supports_tools": model_template.supports_tools,
                "supports_streaming": model_template.supports_streaming,
                "supports_vision": model_template.supports_vision,
                "supports_json_schema": model_template.supports_json_schema,
                "supports_reasoning": model_template.supports_reasoning,
                "metadata": {"source": "provider_template"},
            },
        )

    async def _upsert_model_from_discovered(self, provider: LlmProvider, item: dict[str, Any]):
        existing = await self.model_repo.get_by_provider_model(
            provider_id=str(provider.id),
            model_id=item["model_id"],
        )
        values = {
            "display_name": item["display_name"],
            "context_length": item["context_length"],
            "max_output_tokens": item["max_output_tokens"],
            "supports_tools": item.get("supports_tools", True),
            "supports_streaming": item.get("supports_streaming", True),
            "supports_vision": item.get("supports_vision", False),
            "supports_json_schema": item.get("supports_json_schema", True),
            "supports_reasoning": item["supports_reasoning"],
            "model_metadata": item["metadata"],
            "default_temperature": None,
            "default_top_p": None,
            "cost_metadata": None,
        }
        if existing:
            return await self.model_repo.update_all(existing, **values)
        return await self.model_repo.create(
            provider_id=str(provider.id),
            model_id=item["model_id"],
            **values,
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
    template = provider_template_for_provider(provider)
    if template is not None and not template.api_key_required:
        return False
    return provider.kind != "ollama"


def _provider_discovery_base_url(provider: LlmProvider) -> str | None:
    template = provider_template_for_provider(provider)
    discovery = template.discovery if template else "openai_models"
    if discovery == "ollama_tags":
        return normalize_ollama_base_url(
            provider.base_url or settings.ollama_base_url
        )
    return provider.base_url or (template.default_base_url if template else None)


def _clean_model_ids(raw_model_ids: Any) -> list[str]:
    if not isinstance(raw_model_ids, list):
        return []
    model_ids: list[str] = []
    seen: set[str] = set()
    for item in raw_model_ids:
        model_id = str(item or "").strip()
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        model_ids.append(model_id)
    return model_ids


def _drop_request_tenant_fields(data: dict[str, Any]) -> None:
    data.pop("workspace_id", None)
    data.pop("user_id", None)
    data.pop("role", None)


# Reserved DNS suffixes that never resolve on the public internet (RFC 6762
# ``.local``, RFC 8375 ``.home.arpa``, common private-network TLDs, and
# Kubernetes service domains). Plain HTTP to a host under one of these — or to a
# single-label name like a Docker service (``deepseek-v4``) — cannot reach a
# public endpoint, so it is exempt from the HTTPS requirement.
_INTERNAL_HOST_SUFFIXES = (
    ".local",
    ".internal",
    ".intranet",
    ".lan",
    ".home",
    ".home.arpa",
    ".corp",
    ".svc",
    ".test",
)


def _is_internal_http_host(host: str) -> bool:
    """Return True when *host* can only address a non-public endpoint.

    Plain-HTTP provider endpoints are limited to hosts that cannot live on the
    public internet. This keeps the SSRF surface narrow while still supporting
    loopback, private networks, and container/cluster service names (a Docker
    service ``deepseek-v4`` or a Kubernetes ``api.default.svc``).
    """
    if not host:
        return False
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        normalized = host.rstrip(".").lower()
        # A single-label name (no dot) cannot be a public FQDN — it only
        # resolves via local/container DNS. Reserved suffixes are internal too.
        if "." not in normalized:
            return True
        return any(normalized.endswith(suffix) for suffix in _INTERNAL_HOST_SUFFIXES)
    return ip.is_private or ip.is_loopback or ip.is_link_local


def _validate_provider_base_url(
    base_url: str | None,
    *,
    allow_insecure_http: bool = False,
) -> None:
    if not base_url:
        return
    parsed = urlparse(str(base_url).strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Provider endpoint must be an absolute HTTP(S) URL")
    if parsed.scheme == "https":
        return
    if _is_internal_http_host(parsed.hostname or ""):
        return
    if allow_insecure_http:
        return
    raise ValueError(
        "Plain HTTP endpoints are only allowed for local or internal hosts; "
        "use HTTPS or explicitly allow insecure HTTP for public endpoints"
    )


def validate_provider_transport(provider: LlmProvider) -> None:
    _validate_provider_base_url(
        provider.base_url,
        allow_insecure_http=bool(provider.allow_insecure_http),
    )


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


def _openai_models_from_list(payload: Any) -> list[dict[str, Any]]:
    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_models:
        if isinstance(item, str):
            model_id = item.strip()
        elif isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
        else:
            model_id = ""
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(
            {
                "model_id": model_id,
                "display_name": _display_name_for_openai_model(model_id),
                "context_length": None,
                "max_output_tokens": None,
                "supports_tools": True,
                "supports_streaming": True,
                "supports_vision": False,
                "supports_json_schema": True,
                "supports_reasoning": _model_id_suggests_reasoning(model_id),
                "metadata": {"source": "openai_models_discovery"},
            }
        )
    return models


def _display_name_for_openai_model(model_id: str) -> str:
    if "/" in model_id:
        model_id = model_id.rsplit("/", 1)[-1]
    return " ".join(part.upper() if part.isdigit() else part.capitalize() for part in model_id.replace("_", "-").split("-"))


def _anthropic_models_from_list(payload: Any) -> list[dict[str, Any]]:
    raw_models = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_models:
        if isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
            display_name = str(item.get("display_name") or "").strip()
        else:
            model_id = str(item or "").strip()
            display_name = ""
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        models.append(
            {
                "model_id": model_id,
                "display_name": display_name or _display_name_for_openai_model(model_id),
                "context_length": None,
                "max_output_tokens": None,
                "supports_tools": True,
                "supports_streaming": True,
                "supports_vision": True,
                "supports_json_schema": True,
                "supports_reasoning": _model_id_suggests_reasoning(model_id),
                "metadata": {"source": "anthropic_models_discovery"},
            }
        )
    return models


def _gemini_models_from_list(payload: Any) -> list[dict[str, Any]]:
    raw_models = payload.get("models") if isinstance(payload, dict) else None
    if not isinstance(raw_models, list):
        return []
    models: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in raw_models:
        if not isinstance(item, dict):
            continue
        methods = item.get("supportedGenerationMethods")
        if isinstance(methods, list) and "generateContent" not in methods:
            continue
        name = str(item.get("name") or "").strip()
        model_id = name.split("/", 1)[-1] if name else ""
        if not model_id or model_id in seen:
            continue
        seen.add(model_id)
        display_name = str(item.get("displayName") or "").strip()
        context_length = item.get("inputTokenLimit")
        max_output = item.get("outputTokenLimit")
        models.append(
            {
                "model_id": model_id,
                "display_name": display_name or _display_name_for_openai_model(model_id),
                "context_length": context_length if isinstance(context_length, int) else None,
                "max_output_tokens": max_output if isinstance(max_output, int) else None,
                "supports_tools": True,
                "supports_streaming": True,
                "supports_vision": True,
                "supports_json_schema": True,
                "supports_reasoning": _model_id_suggests_reasoning(model_id),
                "metadata": {"source": "gemini_models_discovery"},
            }
        )
    return models


def _model_id_suggests_reasoning(model_id: str) -> bool:
    normalized = model_id.lower()
    return any(token in normalized for token in ("reason", "thinking", "deepseek-r1", "o1", "o3"))


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
