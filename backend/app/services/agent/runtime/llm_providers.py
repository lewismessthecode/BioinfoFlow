"""Provider selection, credential resolution, and retry logic for LLM calls.

Extracted from llm_client.py to keep each module under 400 lines.
"""

from __future__ import annotations

import asyncio
import json
import os
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, TypeVar

from app.config import settings
from app.services.agent.runtime.providers import (
    PROVIDER_REGISTRY,
    infer_provider_from_model,
    litellm_model_name,
    normalize_openai_compatible_base_url,
)
from app.utils.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

_LLM_REQUEST_TIMEOUT = 120.0

_RETRYABLE_ERRORS = (
    "APIConnectionError",
    "APITimeoutError",
    "RateLimitError",
    "InternalServerError",
    "ServiceUnavailableError",
    "TimeoutError",
    "MidStreamFallbackError",
)
_RETRYABLE_ERROR_SUBSTRINGS = (
    "503",
    "service unavailable",
    "high demand",
    "midstreamfallbackerror",
    "vertex_ai_betaexception",
    "temporarily unavailable",
)
_PROVIDER_EXHAUSTED_SUBSTRINGS = (
    "resource_exhausted",
    "prepayment credits are depleted",
    "quota exceeded",
    "billing",
)


@dataclass(frozen=True)
class LLMProviderAttempt:
    provider: str
    model: str
    litellm_model: str
    api_key: str | None = None
    api_base: str | None = None
    supports_reasoning_effort: bool = False


def is_retryable_llm_exception(exc: Exception) -> bool:
    """Check if an LLM exception is transient and worth retrying."""
    if is_provider_exhausted_exception(exc):
        return True
    if type(exc).__name__ in _RETRYABLE_ERRORS:
        return True
    lowered = str(exc).lower()
    return any(fragment in lowered for fragment in _RETRYABLE_ERROR_SUBSTRINGS)


def is_provider_exhausted_exception(exc: Exception) -> bool:
    """Check if a provider/account is exhausted rather than transiently busy."""
    lowered = str(exc).lower()
    return any(fragment in lowered for fragment in _PROVIDER_EXHAUSTED_SUBSTRINGS)


async def retry_llm_call(
    coro_factory: Callable[[], Coroutine[Any, Any, T]],
    *,
    max_retries: int = 2,
    base_delay: float = 1.0,
) -> T:
    """Retry transient LLM errors with exponential backoff."""
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return await coro_factory()
        except Exception as exc:
            if is_provider_exhausted_exception(exc):
                raise
            if not is_retryable_llm_exception(exc):
                raise
            last_exc = exc
            if attempt == max_retries:
                raise
            delay = base_delay * (2**attempt)
            logger.warning(
                "llm.retry",
                attempt=attempt + 1,
                max_retries=max_retries,
                delay=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
    raise last_exc  # type: ignore[misc]


def resolve_provider_model(provider: str) -> str | None:
    """Resolve model name for a provider from env vars or registry default."""
    if provider == "anthropic" and settings.agent_model:
        return settings.agent_model
    cfg = PROVIDER_REGISTRY.get(provider)
    return cfg.default_model if cfg else None


def select_provider() -> str | None:
    """Select LLM provider based on env var availability (sorted by priority)."""
    provider = (settings.agent_provider or "auto").strip().lower()

    available: list[str] = []
    for name, cfg in sorted(PROVIDER_REGISTRY.items(), key=lambda x: x[1].priority):
        if cfg.credential_type == "base_url_only":
            if os.getenv(cfg.env_base_url_var):
                available.append(name)
        elif cfg.static_api_key and cfg.base_url:
            available.append(name)
        elif cfg.env_key_var:
            env_val = os.getenv(cfg.env_key_var)
            if name == "anthropic":
                env_val = env_val or os.getenv("ANTHROPIC_AUTH_TOKEN")
            if env_val:
                available.append(name)

    if provider in {"auto", ""}:
        return available[0] if available else None
    if provider not in available:
        return available[0] if available else None
    return provider


def resolve_credentials(
    provider: str,
    user_settings: Any,
    *,
    current_provider: str | None = None,
) -> tuple[str | None, str | None]:
    """Resolve API key and base URL from JSON creds -> env vars -> registry defaults."""
    cfg = PROVIDER_REGISTRY.get(provider or "")
    if not cfg:
        return None, None

    api_key: str | None = None
    api_base: str | None = cfg.base_url or None

    # Parse JSON credentials from user settings
    user_creds: dict[str, str] = {}
    if user_settings:
        try:
            all_creds = json.loads(user_settings.provider_credentials or "{}")
            user_creds = all_creds.get(provider, {})
        except (json.JSONDecodeError, TypeError):
            pass

    # Special case: Anthropic AUTH_TOKEN (Bedrock/Vertex)
    if provider == "anthropic":
        auth_token = os.getenv("ANTHROPIC_AUTH_TOKEN")
        if auth_token:
            api_key = auth_token
        elif user_creds.get("api_key"):
            api_key = user_creds["api_key"]
        else:
            api_key = os.getenv(cfg.env_key_var) or None
    elif (current_provider or provider) == "ollama":
        api_key = "ollama"
        api_base = normalize_openai_compatible_base_url(
            user_creds.get("base_url") or os.getenv(cfg.env_base_url_var) or cfg.base_url or "",
            prefer_loopback_ip=True,
        ) or None
    else:
        # Generic: user JSON -> env var
        api_key = (
            user_creds.get("api_key")
            or cfg.static_api_key
            or (os.getenv(cfg.env_key_var) if cfg.env_key_var else None)
            or None
        )
        if user_creds.get("base_url"):
            api_base = user_creds["base_url"]
        elif cfg.env_base_url_var:
            api_base = os.getenv(cfg.env_base_url_var) or api_base
        if cfg.prefix == "openai/" and api_base:
            api_base = normalize_openai_compatible_base_url(api_base)

    return api_key, api_base


def resolve_provider_attempts(
    *,
    model_override: str | None,
    user_settings: Any,
    current_provider: str | None = None,
) -> list[LLMProviderAttempt]:
    """Build ordered list of provider attempts with fallback chain."""
    attempts: list[LLMProviderAttempt] = []
    seen: set[tuple[str, str]] = set()

    def add_attempt(provider: str | None, model: str | None) -> None:
        if not provider or not model:
            return
        cfg = PROVIDER_REGISTRY.get(provider)
        if not cfg:
            return
        key = (provider, model)
        if key in seen:
            return
        api_key, api_base = resolve_credentials(
            provider, user_settings, current_provider=current_provider
        )
        if provider != "ollama" and not api_key and provider != "test":
            return
        attempts.append(
            LLMProviderAttempt(
                provider=provider,
                model=model,
                litellm_model=litellm_model_name(provider, model),
                api_key=api_key,
                api_base=api_base,
                supports_reasoning_effort=cfg.supports_reasoning_effort,
            )
        )
        seen.add(key)

    if model_override:
        override_provider = infer_provider_from_model(model_override)
        add_attempt(override_provider, model_override)
    elif user_settings and user_settings.selected_provider not in ("auto", ""):
        primary_provider = user_settings.selected_provider
        add_attempt(
            primary_provider,
            user_settings.selected_model or resolve_provider_model(primary_provider),
        )
    elif user_settings:
        primary_provider = auto_select_user_provider(user_settings) or select_provider()
        add_attempt(
            primary_provider,
            user_settings.selected_model or resolve_provider_model(primary_provider or ""),
        )
    else:
        primary_provider = select_provider()
        add_attempt(primary_provider, resolve_provider_model(primary_provider or ""))

    for provider, cfg in sorted(PROVIDER_REGISTRY.items(), key=lambda item: item[1].priority):
        if attempts and provider == attempts[0].provider:
            continue
        add_attempt(provider, resolve_provider_model(provider))

    return attempts


def auto_select_user_provider(user_settings: Any) -> str | None:
    """Pick the first user-configured provider (sorted by registry priority)."""
    try:
        creds = json.loads(user_settings.provider_credentials or "{}")
    except (json.JSONDecodeError, TypeError):
        return None

    for name, cfg in sorted(PROVIDER_REGISTRY.items(), key=lambda x: x[1].priority):
        provider_creds = creds.get(name, {})
        if cfg.credential_type == "base_url_only":
            if provider_creds.get("base_url") or provider_creds.get("model"):
                return name
        elif provider_creds.get("api_key"):
            return name
    return None
