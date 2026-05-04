"""Service layer for user LLM settings — registry-driven, JSON credentials."""

from __future__ import annotations

import json
import os

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.user_settings_repo import UserSettingsRepository
from app.schemas.user_settings import (
    ModelInfo,
    ProviderModels,
    ProviderTestResult,
    UserSettingsRead,
    UserSettingsUpdate,
)
from app.services.agent.runtime.providers import (
    PROVIDER_REGISTRY,
    normalize_openai_compatible_base_url,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)


# ── Helpers ─────────────────────────────────────────────────────────

def _mask_key(key: str) -> str:
    """Mask an API key: 'sk-ant-api03-abc...xyz' → 'sk-a...xyz'."""
    if not key:
        return ""
    if len(key) <= 8:
        return key[:2] + "..." + key[-2:]
    return key[:4] + "..." + key[-4:]


def _parse_credentials(raw: str) -> dict[str, dict[str, str]]:
    """Parse the provider_credentials JSON column, tolerant of bad data."""
    if not raw:
        return {}
    try:
        return json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return {}


def _mask_credentials(creds: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Mask any field containing 'key' in its name."""
    masked: dict[str, dict[str, str]] = {}
    for provider, fields in creds.items():
        masked[provider] = {}
        for field_name, value in fields.items():
            if "key" in field_name:
                masked[provider][field_name] = _mask_key(value)
            else:
                masked[provider][field_name] = value
    return masked


def _provider_has_credentials(
    provider: str,
    creds: dict[str, dict[str, str]],
) -> bool:
    """Check if a provider has usable credentials in the JSON blob."""
    cfg = PROVIDER_REGISTRY.get(provider)
    if not cfg:
        return False

    provider_creds = creds.get(provider, {})
    if cfg.credential_type == "base_url_only":
        return bool(provider_creds.get("base_url") or provider_creds.get("model"))
    return bool(provider_creds.get("api_key"))


def _provider_has_env_credentials(provider: str) -> bool:
    """Check if a provider has credentials from environment variables."""
    cfg = PROVIDER_REGISTRY.get(provider)
    if not cfg:
        return False

    if cfg.credential_type == "base_url_only":
        return bool(os.getenv(cfg.env_base_url_var))
    if cfg.static_api_key and cfg.base_url:
        return True
    if provider == "anthropic":
        return bool(os.getenv(cfg.env_key_var) or os.getenv("ANTHROPIC_AUTH_TOKEN"))
    return bool(os.getenv(cfg.env_key_var)) if cfg.env_key_var else False


# ── Service ─────────────────────────────────────────────────────────

class UserSettingsService:
    def __init__(self, session: AsyncSession):
        self.repo = UserSettingsRepository(session)

    async def get_settings(self, user_id: str) -> UserSettingsRead:
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return UserSettingsRead(
                provider_credentials={},
                selected_provider="auto",
                selected_model="",
                configured_providers=[],
            )

        creds = _parse_credentials(settings.provider_credentials)
        configured = [
            p for p in PROVIDER_REGISTRY
            if _provider_has_credentials(p, creds)
        ]

        return UserSettingsRead(
            provider_credentials=_mask_credentials(creds),
            selected_provider=settings.selected_provider or "auto",
            selected_model=settings.selected_model or "",
            configured_providers=configured,
        )

    async def update_settings(
        self, user_id: str, data: UserSettingsUpdate
    ) -> UserSettingsRead:
        # Build the raw update dict for non-credential fields
        update_data: dict = {}
        if data.selected_provider is not None:
            update_data["selected_provider"] = data.selected_provider
        if data.selected_model is not None:
            update_data["selected_model"] = data.selected_model

        # Merge provider_credentials (partial merge, not full overwrite)
        if data.provider_credentials is not None:
            existing = await self.repo.get_by_user_id(user_id)
            current_creds = _parse_credentials(
                existing.provider_credentials if existing else "{}"
            )
            for provider, fields in data.provider_credentials.items():
                if provider not in current_creds:
                    current_creds[provider] = {}
                for k, v in fields.items():
                    if v == "":
                        current_creds[provider].pop(k, None)
                    else:
                        current_creds[provider][k] = v
                # Clean up empty provider entries
                if not current_creds[provider]:
                    del current_creds[provider]
            update_data["provider_credentials"] = json.dumps(current_creds)

        await self.repo.upsert(user_id, **update_data)
        return await self.get_settings(user_id)

    async def get_raw_key(self, user_id: str, provider: str) -> str:
        """Get the unmasked API key for a provider (used by LLMClient)."""
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return ""
        creds = _parse_credentials(settings.provider_credentials)
        return creds.get(provider, {}).get("api_key", "")

    async def get_raw_credentials(self, user_id: str, provider: str) -> dict[str, str]:
        """Get all unmasked credentials for a provider."""
        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return {}
        creds = _parse_credentials(settings.provider_credentials)
        return creds.get(provider, {})

    async def test_provider(
        self, user_id: str, provider: str
    ) -> ProviderTestResult:
        """Test a provider's API key with a minimal API call."""
        cfg = PROVIDER_REGISTRY.get(provider)
        if not cfg:
            return ProviderTestResult(
                provider=provider, success=False, error=f"Unknown provider: {provider}"
            )

        settings = await self.repo.get_by_user_id(user_id)
        if not settings:
            return ProviderTestResult(
                provider=provider, success=False, error="No settings configured"
            )

        creds = _parse_credentials(settings.provider_credentials)
        provider_creds = creds.get(provider, {})

        # Dispatch based on test_protocol from registry
        try:
            if cfg.test_protocol == "ollama":
                model = provider_creds.get("model") or cfg.default_model
                base_url = normalize_openai_compatible_base_url(
                    provider_creds.get("base_url") or os.getenv(cfg.env_base_url_var) or cfg.base_url,
                    prefer_loopback_ip=True,
                )
                result = await self._test_openai("ollama", base_url, model)
                return ProviderTestResult(
                    provider=provider, success=True,
                    model=result.model or model,
                )
            elif cfg.test_protocol == "anthropic":
                api_key = provider_creds.get("api_key", "")
                if not api_key:
                    return ProviderTestResult(
                        provider=provider, success=False, error="No API key configured"
                    )
                return await self._test_anthropic(api_key)
            elif cfg.test_protocol == "gemini":
                api_key = provider_creds.get("api_key", "")
                if not api_key:
                    return ProviderTestResult(
                        provider=provider, success=False, error="No API key configured"
                    )
                return await self._test_gemini(api_key)
            else:
                # OpenAI-compatible (openai, deepseek, qwen, kimi, minimax, openrouter)
                api_key = provider_creds.get("api_key", "")
                if not api_key and cfg.static_api_key:
                    api_key = cfg.static_api_key
                if not api_key:
                    return ProviderTestResult(
                        provider=provider, success=False, error="No API key configured"
                    )
                base_url = provider_creds.get("base_url") or cfg.base_url or "https://api.openai.com/v1"
                if cfg.prefix == "openai/":
                    base_url = normalize_openai_compatible_base_url(base_url)
                model = provider_creds.get("model")
                if cfg.prefix == "openai/" or model:
                    model = model or cfg.default_model
                result = await self._test_openai(api_key, base_url, model)
                return ProviderTestResult(
                    provider=provider,
                    success=result.success,
                    error=result.error,
                    model=result.model,
                )
        except Exception as exc:
            logger.warning("Provider test failed", provider=provider, error=str(exc))
            return ProviderTestResult(
                provider=provider, success=False, error=str(exc)
            )

    async def get_available_models(self, user_id: str) -> list[ProviderModels]:
        """Return models for providers that have credentials (user or env)."""
        settings = await self.repo.get_by_user_id(user_id)
        creds = _parse_credentials(
            settings.provider_credentials if settings else "{}"
        )

        result = []
        for provider, cfg in PROVIDER_REGISTRY.items():
            if not cfg.models:
                # Dynamic providers (ollama) — only show if configured
                if not _provider_has_credentials(provider, creds) and not _provider_has_env_credentials(provider):
                    continue
            else:
                if not _provider_has_credentials(provider, creds) and not _provider_has_env_credentials(provider):
                    continue

            provider_creds = creds.get(provider, {})
            models: list[ModelInfo] = []
            custom_model = provider_creds.get("model")
            seen_models: set[str] = set()
            if custom_model:
                models.append(
                    ModelInfo(id=custom_model, name=custom_model, context_window=None)
                )
                seen_models.add(custom_model)
            models.extend(
                ModelInfo(id=m.id, name=m.name, context_window=m.context_window)
                for m in cfg.models
                if m.id not in seen_models
            )
            result.append(ProviderModels(
                provider=provider,
                label=cfg.label,
                models=models,
            ))

        return result

    # --- Provider test helpers ---

    async def _test_anthropic(self, api_key: str) -> ProviderTestResult:
        import os
        from anthropic import AsyncAnthropic

        auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
        if auth_token:
            client = AsyncAnthropic(api_key=None, auth_token=auth_token)
        else:
            client = AsyncAnthropic(api_key=api_key, auth_token=None)

        response = await client.messages.create(
            model="claude-haiku-4-5",
            max_tokens=1,
            messages=[{"role": "user", "content": "ping"}],
        )
        return ProviderTestResult(
            provider="anthropic",
            success=True,
            model=response.model,
        )

    async def _test_openai(
        self,
        api_key: str,
        base_url: str,
        model: str | None = None,
    ) -> ProviderTestResult:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
        )
        if model:
            response = await client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": "ping"}],
                max_tokens=1,
            )
            return ProviderTestResult(
                provider="openai",
                success=True,
                model=response.model,
            )
        models = await client.models.list()
        return ProviderTestResult(
            provider="openai",
            success=True,
            model=models.data[0].id if models.data else None,
        )

    async def _test_gemini(self, api_key: str) -> ProviderTestResult:
        import httpx

        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key},
                timeout=10.0,
            )
            resp.raise_for_status()
        return ProviderTestResult(provider="gemini", success=True)
