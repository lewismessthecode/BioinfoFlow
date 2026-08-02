"""Model selection and fallback resolution for Agent Core turns.

The resolver owns the catalog, credential, transport, and target-revision
rules needed to turn a requested model selection into an executable model
target. ``AgentCoreRuntime`` keeps compatibility delegators for callers that
still use its historical private methods.
"""

from __future__ import annotations

from typing import Any

from app.services.agent_core.core.fallback import build_fallback_model_ids
from app.services.agent_core.core.runtime_strategy import (
    RuntimeStrategy,
    capabilities_from_model,
    resolve_runtime_strategy,
)
from app.services.agent_core.model_selection import (
    normalize_model_selection,
    session_model_selection_from_metadata,
)
from app.services.authorization_service import AuthorizationService
from app.services.llm.access_policy import (
    authorize_server_environment_credential,
    provider_has_server_integration_authority,
    resolve_provider_network_access,
)
from app.services.llm.catalog import _provider_requires_credential, validate_provider_transport
from app.services.llm.credentials import (
    credential_available,
    credential_configured,
    derive_model_target_revision,
    resolve_credential_material,
)
from app.services.llm.provider_templates import (
    normalize_provider_base_url,
    route_provider_model_name,
)
from app.utils.exceptions import PermissionDeniedError


_DEFAULT_PREFERRED_ENV_KINDS = {"vllm", "openai_compatible"}


class AgentModelResolver:
    """Resolve requested, resumed, default, and fallback model candidates."""

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

    async def resolve_selection(self, *, turn, session) -> dict[str, Any] | None:
        snapshot = turn.model_profile_snapshot or {}
        candidates: list[tuple[str, dict[str, str] | None]] = [
            (
                "turn_profile",
                normalize_model_selection(
                    {"profile_id": snapshot.get("requested_model_profile_id")}
                ),
            ),
            (
                "turn",
                normalize_model_selection(snapshot.get("requested_model_selection")),
            ),
            (
                "session",
                session_model_selection_from_metadata(
                    getattr(session, "session_metadata", None)
                ),
            ),
            (
                "session_profile",
                normalize_model_selection(
                    {"profile_id": session.default_model_profile_id}
                ),
            ),
        ]
        for source, selection in candidates:
            catalog = await self.catalog_selection(
                selection,
                source=source,
                workspace_id=str(session.workspace_id),
                user_id=turn.user_id,
            )
            if catalog:
                return catalog
            if (
                selection
                and (selection.get("model_id") or selection.get("profile_id"))
            ):
                return None
        return await self.catalog_default_selection(
            workspace_id=str(session.workspace_id),
            user_id=turn.user_id,
        )

    async def resolve_resume_selection(
        self,
        *,
        turn,
        session,
    ) -> dict[str, Any] | None:
        snapshot = turn.model_profile_snapshot or {}
        resolved_model_id = snapshot.get("resolved_model_id")
        if not resolved_model_id:
            return await self.resolve_selection(turn=turn, session=session)
        candidate = await self.catalog_selection(
            {"model_id": str(resolved_model_id)},
            source="turn_resolved_resume",
            workspace_id=str(session.workspace_id),
            user_id=turn.user_id,
        )
        if candidate is None:
            return None
        resolved_target = snapshot.get("resolved_model_target")
        if isinstance(resolved_target, dict):
            if not target_identity_matches_snapshot(
                candidate,
                resolved_target,
                expected_target_revision=snapshot.get(
                    "_resolved_model_target_revision"
                ),
            ):
                return None
        capabilities = snapshot.get("resolved_model_capabilities")
        if isinstance(capabilities, dict):
            candidate["capabilities"] = capabilities
        runtime_strategy = snapshot.get("resolved_runtime_strategy")
        if isinstance(runtime_strategy, dict):
            candidate["runtime_strategy"] = runtime_strategy
        return candidate

    async def catalog_selection(
        self,
        selection: dict[str, str] | None,
        *,
        source: str,
        workspace_id: str,
        user_id: str,
    ) -> dict[str, Any] | None:
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
        if not model_id:
            return None
        model = await self.llm_models.get_visible(
            model_id,
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
            network_access = await resolve_provider_network_access(
                provider.base_url,
                private_endpoint_authorized=server_authorized,
                resolve_dns=not server_authorized,
            )
        except PermissionDeniedError:
            return None
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
        routed_model_name = route_provider_model_name(
            provider.kind,
            model.model_id,
            wire_protocol=wire_protocol,
        )
        normalized_base_url = (
            normalize_provider_base_url(provider.kind, provider.base_url)
            if provider.base_url
            else None
        )
        target_revision = derive_model_target_revision(
            endpoint_id=str(provider.id),
            provider_kind=str(provider.kind),
            model_name=str(model.model_id),
            wire_protocol=wire_protocol,
            routed_model_name=routed_model_name,
            base_url=normalized_base_url,
            credential_material=material,
        )
        request_args: dict[str, Any] = {}
        if material.api_key:
            request_args["api_key"] = material.api_key
        if normalized_base_url:
            request_args["api_base"] = normalized_base_url
        capabilities = capabilities_from_model(model)
        runtime_strategy = resolve_runtime_strategy(
            capabilities=capabilities,
            profile=profile if profile_id else None,
        )
        result = {
            "endpoint_id": str(provider.id),
            "provider": provider.kind,
            "model": model.model_id,
            "routed_model_name": routed_model_name,
            "model_id": str(model.id),
            "source": source,
            "capabilities": capabilities.as_dict(),
            "runtime_strategy": runtime_strategy.as_dict(),
            "request_args": request_args,
            "wire_protocol": wire_protocol,
            "target_revision": target_revision,
            "network_access": network_access,
        }
        if profile_id:
            result["profile_id"] = profile_id
        return result

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

    async def resolve_fallback_candidates(
        self,
        *,
        turn,
        session,
        resolved: dict[str, Any],
    ) -> list[dict[str, Any]]:
        runtime_strategy = resolved_runtime_strategy(resolved)
        fallback_model_ids = build_fallback_model_ids(
            runtime_strategy.fallback_model_ids,
            primary_model_id=resolved.get("model_id"),
        )
        candidates: list[dict[str, Any]] = []
        for model_id in fallback_model_ids:
            candidate = await self.catalog_selection(
                {"model_id": model_id},
                source="fallback_model",
                workspace_id=str(session.workspace_id),
                user_id=turn.user_id,
            )
            if candidate is not None:
                candidates.append(candidate)
        return candidates


def default_provider_rank(provider) -> int:
    """Rank providers within a scope, preferring explicit env-managed vLLM."""
    metadata = provider.provider_metadata or {}
    if (
        metadata.get("envManaged") is True
        and provider.kind in _DEFAULT_PREFERRED_ENV_KINDS
    ):
        return 0
    return 1


def target_identity_matches_snapshot(
    resolved: dict[str, Any],
    snapshot: dict[str, Any],
    *,
    expected_target_revision: object,
) -> bool:
    if not isinstance(expected_target_revision, str) or not expected_target_revision:
        return False
    request_args = resolved.get("request_args") or {}
    return resolved.get("target_revision") == expected_target_revision and {
        "endpoint_id": str(resolved.get("endpoint_id") or ""),
        "provider_kind": resolved.get("provider"),
        "model_name": resolved.get("model"),
        "wire_protocol": resolved.get("wire_protocol") or "chat_completions",
        "base_url": request_args.get("api_base"),
    } == {
        "endpoint_id": snapshot.get("endpoint_id"),
        "provider_kind": snapshot.get("provider_kind"),
        "model_name": snapshot.get("model_name"),
        "wire_protocol": snapshot.get("wire_protocol") or "chat_completions",
        "base_url": snapshot.get("base_url"),
    }


def resolved_runtime_strategy(
    resolved: dict[str, Any],
) -> RuntimeStrategy:
    strategy = resolved.get("runtime_strategy")
    if not isinstance(strategy, dict):
        return RuntimeStrategy()
    fallback_model_ids = strategy.get("fallback_model_ids") or []
    return RuntimeStrategy(
        use_streaming=bool(strategy.get("use_streaming", True)),
        allow_thinking=bool(strategy.get("allow_thinking", True)),
        allow_tools=bool(strategy.get("allow_tools", True)),
        max_tokens=_coerce_optional_int(strategy.get("max_tokens")),
        reasoning_budget=_coerce_optional_int(strategy.get("reasoning_budget")),
        reasoning_effort=(
            strategy.get("reasoning_effort")
            if strategy.get("reasoning_effort") in {"low", "medium", "high"}
            else None
        ),
        fallback_model_ids=tuple(str(item) for item in fallback_model_ids),
    )


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


__all__ = [
    "AgentModelResolver",
    "default_provider_rank",
    "resolved_runtime_strategy",
    "target_identity_matches_snapshot",
]
