"""Resolve a Harness model selection into one executable model target."""

from __future__ import annotations

from typing import Any

from app.services.agent_harness.runtime_strategy import (
    RuntimeCapabilities,
    RuntimeStrategy,
    capabilities_from_model,
    resolve_runtime_strategy,
    runtime_strategy_from_mapping,
)
from app.services.agent_harness.model_selection import normalize_model_selection
from app.services.authorization_service import AuthorizationService
from app.services.llm.access_policy import (
    authorize_server_environment_credential,
    provider_has_server_integration_authority,
)
from app.services.llm.catalog import (
    _provider_requires_credential,
    validate_provider_transport,
)
from app.services.llm.credentials import (
    credential_available,
    credential_configured,
    resolve_credential_material,
)
from app.services.llm.target_resolution import resolve_model_target
from app.utils.exceptions import PermissionDeniedError


_DEFAULT_PREFERRED_ENV_KINDS = {"vllm", "openai_compatible"}


class AgentModelResolver:
    """Resolve one current Session or catalog model target."""

    def __init__(
        self,
        *,
        llm_models,
        llm_profiles,
        llm_providers,
        llm_credentials,
        authorization: AuthorizationService,
    ) -> None:
        self.llm_models = llm_models
        self.llm_profiles = llm_profiles
        self.llm_providers = llm_providers
        self.llm_credentials = llm_credentials
        self.authorization = authorization

    async def catalog_selection(
        self,
        selection: dict[str, str] | None,
        *,
        source: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        selection = normalize_model_selection(selection)
        if not selection:
            return None
        profile_id = selection.get("profile_id")
        model_id = selection.get("model_id")
        profile = None
        if profile_id:
            profile = await self.llm_profiles.get_visible(
                profile_id,
                workspace_id=workspace_id,
                user_id=user_id,
                enabled_only=True,
            )
            if profile is None:
                return None
            model_id = str(profile.primary_model_id)
        if model_id:
            model = await self.llm_models.get_visible(
                model_id,
                workspace_id=workspace_id,
                user_id=user_id,
            )
        else:
            model = await self._provider_model(
                provider_ref=selection.get("provider"),
                model_name=selection.get("model"),
                workspace_id=workspace_id,
                user_id=user_id,
            )
        if model is None:
            return None
        provider = await self.llm_providers.get_visible(
            str(model.provider_id),
            workspace_id=workspace_id,
            user_id=user_id,
            enabled_only=True,
        )
        if provider is None:
            return None
        role = await self.authorization.resolve_workspace_role(
            workspace_id=workspace_id,
            user_id=user_id,
        )
        server_authorized = provider_has_server_integration_authority(
            provider,
            role=role,
        )
        try:
            validate_provider_transport(provider)
        except ValueError:
            return None
        credential = await self.llm_credentials.get_for_provider(str(provider.id))
        if (
            not server_authorized
            and credential is not None
            and credential.source == "env"
        ):
            try:
                authorize_server_environment_credential(role=role)
            except PermissionDeniedError:
                return None
        if not credential_available(
            credential,
            credential_required=_provider_requires_credential(provider),
        ):
            return None
        material = resolve_credential_material(credential)
        wire_protocol = str(getattr(provider, "wire_protocol", "chat_completions"))
        try:
            target = await resolve_model_target(
                endpoint_id=str(provider.id),
                provider_kind=str(provider.kind),
                model_name=str(model.model_id),
                wire_protocol=wire_protocol,
                base_url=provider.base_url,
                provider_metadata=provider.provider_metadata,
                credential=material,
                private_endpoint_authorized=server_authorized,
                resolve_dns=not server_authorized,
            )
        except PermissionDeniedError:
            return None
        request_args: dict[str, Any] = {}
        if target.resolved_api_key():
            request_args["api_key"] = target.resolved_api_key()
        if target.base_url:
            request_args["api_base"] = target.base_url
        capabilities = capabilities_from_model(model)
        runtime_strategy = resolve_runtime_strategy(
            capabilities=capabilities,
            profile=profile if profile_id else None,
        )
        result = {
            "endpoint_id": str(provider.id),
            "provider": provider.kind,
            "model": model.model_id,
            "routed_model_name": target.resolved_model_name(),
            "model_id": str(model.id),
            "source": source,
            "capabilities": capabilities.as_dict(),
            "runtime_strategy": runtime_strategy.as_dict(),
            "request_args": request_args,
            "wire_protocol": wire_protocol,
            "target_revision": target.resolved_target_revision(),
            "network_access": target.network_access,
        }
        if profile_id:
            result["profile_id"] = profile_id
        return result

    async def resolve_snapshot(
        self,
        snapshot: dict[str, Any] | None,
        *,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        """Refresh private target material without changing session policy."""

        if not isinstance(snapshot, dict):
            return None
        model_id = snapshot.get("model_id")
        profile_id = snapshot.get("profile_id")
        if isinstance(model_id, str) and model_id:
            selection = {"model_id": model_id}
        elif isinstance(profile_id, str) and profile_id:
            selection = {"profile_id": profile_id}
        else:
            return None
        resolved = await self.catalog_selection(
            selection,
            source="session_runtime",
            workspace_id=workspace_id,
            user_id=user_id,
        )
        if resolved is None:
            return None
        capabilities = snapshot.get("capabilities")
        if isinstance(capabilities, dict):
            resolved["capabilities"] = dict(capabilities)
        runtime_strategy = snapshot.get("runtime_strategy")
        if isinstance(runtime_strategy, dict):
            resolved["runtime_strategy"] = runtime_strategy_from_mapping(
                runtime_strategy
            ).as_dict()
        if isinstance(snapshot.get("profile_id"), str):
            resolved["profile_id"] = snapshot["profile_id"]
        return resolved

    async def _provider_model(
        self,
        *,
        provider_ref: str | None,
        model_name: str | None,
        workspace_id: str,
        user_id: str,
    ):
        if not provider_ref or not model_name:
            return None
        providers = await self.llm_providers.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
            enabled_only=True,
        )
        normalized_ref = provider_ref.strip().lower()
        matching = [
            provider
            for provider in providers
            if normalized_ref
            in {
                str(provider.id).lower(),
                str(provider.kind).lower(),
                str(provider.name).strip().lower(),
            }
        ]
        matching.sort(
            key=lambda provider: 0 if str(provider.id).lower() == normalized_ref else 1
        )
        for provider in matching:
            model = await self.llm_models.get_by_provider_model(
                provider_id=str(provider.id),
                model_id=model_name,
            )
            if model is None:
                continue
            visible = await self.llm_models.get_visible(
                str(model.id),
                workspace_id=workspace_id,
                user_id=user_id,
            )
            if visible is not None:
                return visible
        return None

    async def catalog_default_selection(
        self,
        *,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
        providers = await self.llm_providers.list_available(
            workspace_id=workspace_id,
            user_id=user_id,
            enabled_only=True,
        )
        for scope in ("user", "workspace", "global"):
            scoped = sorted(
                (provider for provider in providers if provider.scope == scope),
                key=default_provider_rank,
            )
            for provider in scoped:
                credential = await self.llm_credentials.get_for_provider(
                    str(provider.id)
                )
                metadata = provider.provider_metadata or {}
                if scope == "global" and not (
                    metadata.get("envManaged") is True
                    or credential_configured(credential)
                ):
                    continue
                if not credential_available(
                    credential,
                    credential_required=_provider_requires_credential(provider),
                ):
                    continue
                models = await self.llm_models.list_for_provider(str(provider.id))
                for model in models:
                    candidate = await self.catalog_selection(
                        {"model_id": str(model.id)},
                        source="catalog_default",
                        workspace_id=workspace_id,
                        user_id=user_id,
                    )
                    if candidate is not None:
                        return candidate
        return None


def default_provider_rank(provider) -> int:
    """Rank providers within a scope, preferring explicit env-managed vLLM."""
    metadata = provider.provider_metadata or {}
    if (
        metadata.get("envManaged") is True
        and provider.kind in _DEFAULT_PREFERRED_ENV_KINDS
    ):
        return 0
    return 1


def resolved_runtime_strategy(
    resolved: dict[str, Any],
) -> RuntimeStrategy:
    strategy = resolved.get("runtime_strategy")
    return runtime_strategy_from_mapping(strategy)


def resolved_runtime_capabilities(
    resolved: dict[str, Any],
) -> RuntimeCapabilities:
    capabilities = resolved.get("capabilities")
    if not isinstance(capabilities, dict):
        return RuntimeCapabilities()
    return RuntimeCapabilities(
        supports_streaming=bool(capabilities.get("supports_streaming", True)),
        supports_reasoning=bool(capabilities.get("supports_reasoning", False)),
        supports_tools=bool(capabilities.get("supports_tools", True)),
        supports_vision=bool(capabilities.get("supports_vision", False)),
    )


__all__ = [
    "AgentModelResolver",
    "default_provider_rank",
    "resolved_runtime_capabilities",
    "resolved_runtime_strategy",
]
