from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm import LlmCredentialSource, LlmProvider
from app.repositories.llm_repo import (
    LlmModelRepository,
    LlmProviderCredentialRepository,
    LlmProviderRepository,
)
from app.services.llm.access_policy import resolve_provider_network_access
from app.services.llm.catalog import LlmCatalogService
from app.services.llm.provider_templates import (
    ModelTemplate,
    ProviderTemplate,
    list_bootstrap_provider_templates,
    normalize_provider_base_url,
)

logger = logging.getLogger(__name__)

# Bound per-provider model discovery during startup so an unreachable endpoint
# cannot stall boot. Manual discovery from the UI uses the longer default.
_BOOTSTRAP_DISCOVERY_TIMEOUT = 5.0


@dataclass(frozen=True)
class LlmCatalogBootstrapResult:
    created_or_updated: int = 0


async def sync_environment_llm_catalog(
    session: AsyncSession,
) -> LlmCatalogBootstrapResult:
    provider_repo = LlmProviderRepository(session)
    model_repo = LlmModelRepository(session)
    credential_repo = LlmProviderCredentialRepository(session)
    catalog_service = LlmCatalogService(session)
    changed = 0

    for template in list_bootstrap_provider_templates():
        env_api_key_var = _first_present_env_var(template.env_api_key_vars)
        env_base_url_var = _first_present_env_var(template.env_base_url_vars)
        env_allow_insecure_http = _first_truthy_env_value(
            template.env_allow_insecure_http_vars
        )
        env_model = _first_present_env_value(template.env_model_vars)
        env_wire_protocol = _first_present_env_value(template.env_wire_protocol_vars)
        should_sync = bool(
            env_api_key_var or env_base_url_var or env_model or env_wire_protocol
        )
        if template.id in {"vllm", "openai-compatible"}:
            should_sync = bool(env_base_url_var or env_model)
        if not should_sync:
            continue

        wire_protocol = template.validate_wire_protocol(
            env_wire_protocol or template.default_wire_protocol
        )

        base_url = None
        if env_base_url_var:
            base_url = os.getenv(env_base_url_var)
        if not base_url:
            base_url = template.default_base_url
        base_url = normalize_provider_base_url(template.kind, base_url)

        provider = await _get_env_managed_provider(provider_repo, template)
        metadata = {
            **((provider.provider_metadata or {}) if provider else {}),
            "envManaged": True,
            "providerTemplate": template.id,
        }
        name = (
            os.getenv("OPENAI_COMPATIBLE_NAME")
            if template.id == "openai-compatible"
            else None
        )
        name = (name or template.name).strip()

        if provider is None:
            provider = await provider_repo.create(
                name=name,
                kind=template.kind,
                wire_protocol=wire_protocol,
                base_url=base_url,
                api_key_ref=None,
                scope="global",
                workspace_id=None,
                user_id=None,
                enabled=True,
                allow_insecure_http=env_allow_insecure_http,
                provider_metadata=metadata,
            )
            changed += 1
        else:
            provider = await provider_repo.update_all(
                provider,
                name=name,
                kind=template.kind,
                wire_protocol=wire_protocol,
                base_url=base_url,
                enabled=True,
                allow_insecure_http=env_allow_insecure_http,
                provider_metadata=metadata,
            )
            changed += 1

        credential = await credential_repo.get_for_provider(str(provider.id))
        if env_api_key_var:
            payload = {
                "source": LlmCredentialSource.ENV,
                "env_var_name": env_api_key_var,
                "encrypted_secret": None,
                "fingerprint": None,
                "masked_hint": f"env:{env_api_key_var}",
                "updated_by": None,
            }
        elif not template.api_key_required:
            payload = {
                "source": LlmCredentialSource.NONE,
                "env_var_name": None,
                "encrypted_secret": None,
                "fingerprint": None,
                "masked_hint": None,
                "updated_by": None,
            }
        else:
            payload = None
        if payload is not None:
            if credential:
                await credential_repo.update_all(credential, **payload)
            else:
                await credential_repo.create(provider_id=str(provider.id), **payload)

        # Seed only an explicitly configured `*_MODEL` env var as a manual
        # fallback. Real model lists are populated by live discovery below;
        # provider templates no longer carry hardcoded model lists.
        model_templates: list[ModelTemplate] = []
        if env_model:
            model_templates.append(
                ModelTemplate(
                    id=env_model,
                    name=env_model,
                    supports_tools=True,
                    supports_streaming=True,
                    supports_json_schema=True,
                    supports_reasoning=_model_id_suggests_reasoning(env_model),
                ),
            )
        for model_template in _dedupe_model_templates(model_templates):
            existing = await model_repo.get_by_provider_model(
                provider_id=str(provider.id),
                model_id=model_template.id,
            )
            values = {
                "display_name": model_template.name,
                "context_length": model_template.context_length,
                "max_output_tokens": model_template.max_output_tokens,
                "supports_tools": model_template.supports_tools,
                "supports_streaming": model_template.supports_streaming,
                "supports_vision": model_template.supports_vision,
                "supports_json_schema": model_template.supports_json_schema,
                "supports_reasoning": model_template.supports_reasoning,
                "default_temperature": None,
                "default_top_p": None,
                "cost_metadata": None,
                "model_metadata": {"source": "environment_bootstrap"},
            }
            if existing:
                await model_repo.update_all(existing, **values)
            else:
                await model_repo.create(
                    provider_id=str(provider.id),
                    model_id=model_template.id,
                    **values,
                )

        # Best-effort: fetch the real model list for this env-managed provider.
        # Network failures must never break startup — discovery can be retried
        # on demand from the settings UI ("Refresh models"). A short timeout
        # keeps an unreachable endpoint from stalling startup.
        try:
            network_access = await resolve_provider_network_access(
                provider.base_url,
                private_endpoint_authorized=True,
            )
            await catalog_service.discover_models_unchecked(
                provider,
                timeout=_BOOTSTRAP_DISCOVERY_TIMEOUT,
                network_access=network_access,
            )
        except Exception as exc:  # noqa: BLE001 - resilience over precision
            logger.warning(
                "LLM model discovery skipped for %s during bootstrap: %s",
                template.id,
                exc,
            )

    return LlmCatalogBootstrapResult(created_or_updated=changed)


async def _get_env_managed_provider(
    provider_repo: LlmProviderRepository,
    template: ProviderTemplate,
) -> LlmProvider | None:
    providers = await provider_repo.list_available()
    for provider in providers:
        metadata = provider.provider_metadata or {}
        if (
            provider.scope == "global"
            and metadata.get("envManaged") is True
            and metadata.get("providerTemplate") == template.id
        ):
            return provider
    return None


def _first_present_env_var(candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        if os.getenv(name):
            return name
    return None


def _first_present_env_value(candidates: tuple[str, ...]) -> str | None:
    for name in candidates:
        value = os.getenv(name)
        if value:
            return value.strip()
    return None


def _first_truthy_env_value(candidates: tuple[str, ...]) -> bool:
    for name in candidates:
        value = os.getenv(name)
        if value is None:
            continue
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _dedupe_model_templates(models: list[ModelTemplate]) -> list[ModelTemplate]:
    result: list[ModelTemplate] = []
    seen: set[str] = set()
    for model in models:
        if model.id in seen:
            continue
        seen.add(model.id)
        result.append(model)
    return result


def _model_id_suggests_reasoning(model_id: str) -> bool:
    normalized = model_id.lower()
    return any(
        token in normalized
        for token in ("reason", "thinking", "deepseek-r1", "o1", "o3")
    )
