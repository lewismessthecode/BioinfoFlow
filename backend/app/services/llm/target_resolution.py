"""Resolve configured providers into exact executable model targets."""

from __future__ import annotations

from typing import Any

from app.services.llm.access_policy import resolve_provider_network_access
from app.services.llm.credentials import (
    CredentialMaterial,
    derive_model_target_revision,
)
from app.services.llm.provider_templates import (
    get_provider_template,
    normalize_anthropic_base_url,
    normalize_ollama_base_url,
    provider_template_for_kind,
    route_provider_model_name,
)
from app.services.llm.registry import provider_spec_for_kind
from app.services.model_runtime.contracts import (
    ModelTarget,
    NetworkAccessPolicy,
    WireProtocol,
)


def resolve_provider_endpoint(
    provider_kind: str,
    base_url: str | None,
    *,
    provider_metadata: dict[str, Any] | None = None,
) -> str | None:
    """Return the exact endpoint owned by one configured provider.

    Explicit overrides are preserved. Known branded providers fall back to the
    immutable registry endpoint. Compatibility templates are consulted only for
    legacy provider kinds that have not migrated into the registry. No generic
    code guesses or appends an API-version suffix.
    """

    template_id = str((provider_metadata or {}).get("providerTemplate") or "").strip()
    template = get_provider_template(template_id) if template_id else None
    effective_kind = template.kind if template is not None else provider_kind

    candidate = str(base_url or "").strip()
    if not candidate:
        spec = provider_spec_for_kind(effective_kind)
        if spec is not None:
            candidate = spec.endpoint.default_base_url
        else:
            legacy_template = template or provider_template_for_kind(effective_kind)
            if legacy_template is not None and not legacy_template.base_url_required:
                candidate = str(legacy_template.default_base_url or "").strip()
    if not candidate:
        return None
    return _normalize_exact_endpoint(effective_kind, candidate)


async def resolve_model_target(
    *,
    endpoint_id: str,
    provider_kind: str,
    model_name: str,
    wire_protocol: WireProtocol,
    base_url: str | None,
    provider_metadata: dict[str, Any] | None,
    credential: CredentialMaterial,
    private_endpoint_authorized: bool,
    resolve_dns: bool,
) -> ModelTarget:
    """Resolve provider facts, transport policy, routing, and revision once."""

    exact_endpoint = resolve_provider_endpoint(
        provider_kind,
        base_url,
        provider_metadata=provider_metadata,
    )
    network_access = await resolve_provider_network_access(
        exact_endpoint,
        private_endpoint_authorized=private_endpoint_authorized,
        resolve_dns=resolve_dns,
    )
    return build_model_target(
        endpoint_id=endpoint_id,
        provider_kind=provider_kind,
        model_name=model_name,
        wire_protocol=wire_protocol,
        exact_endpoint=exact_endpoint,
        network_access=network_access,
        credential=credential,
    )


def build_model_target(
    *,
    endpoint_id: str,
    provider_kind: str,
    model_name: str,
    wire_protocol: WireProtocol,
    exact_endpoint: str | None,
    network_access: NetworkAccessPolicy,
    credential: CredentialMaterial,
) -> ModelTarget:
    """Build the immutable target consumed by Provider Test and Agent Runtime."""

    routed_model_name = route_provider_model_name(
        provider_kind,
        model_name,
        wire_protocol=wire_protocol,
    )
    target_revision = derive_model_target_revision(
        endpoint_id=endpoint_id,
        provider_kind=provider_kind,
        model_name=model_name,
        wire_protocol=wire_protocol,
        routed_model_name=routed_model_name,
        base_url=exact_endpoint,
        credential_material=credential,
    )
    return ModelTarget(
        endpoint_id=endpoint_id,
        provider_kind=provider_kind,
        model_name=model_name,
        routed_model_name=routed_model_name,
        wire_protocol=wire_protocol,
        base_url=exact_endpoint,
        network_access=network_access,
        api_key=credential.api_key,
        target_revision=target_revision,
    )


def _normalize_exact_endpoint(provider_kind: str, base_url: str) -> str:
    if provider_kind == "ollama":
        return normalize_ollama_base_url(base_url)
    if provider_kind == "anthropic":
        return normalize_anthropic_base_url(base_url)
    return base_url.strip().rstrip("/")


__all__ = [
    "build_model_target",
    "resolve_model_target",
    "resolve_provider_endpoint",
]
