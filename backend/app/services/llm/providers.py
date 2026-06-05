"""LLM provider registry — single source of truth.

Every provider is defined here once. Adding a new provider = adding one entry
to PROVIDER_REGISTRY. No other backend file needs to change (except optionally
adding the env var to .env.example).

All providers are called through LiteLLM's unified API.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ModelEntry:
    """A model offered by a provider."""

    id: str
    name: str
    context_window: int | None = None


@dataclass(frozen=True)
class ProviderConfig:
    """Complete configuration for an LLM provider."""

    # --- Core (LiteLLM routing) ---
    default_model: str
    prefix: str = ""  # LiteLLM model prefix (e.g. "anthropic/", "gemini/")
    base_url: str = ""

    # --- Model catalog ---
    models: list[ModelEntry] = field(default_factory=list)

    # --- Display ---
    label: str = ""  # Human-readable name (e.g. "DeepSeek")

    # --- Credentials ---
    credential_type: str = (
        "api_key"  # "api_key" | "api_key_and_base_url" | "base_url_only"
    )
    env_key_var: str = ""  # Env var for API key (e.g. "DEEPSEEK_API_KEY")
    env_base_url_var: str = ""  # Env var for base URL (e.g. "OLLAMA_BASE_URL")
    static_api_key: str = ""  # For env-declared local/OpenAI-compatible profiles

    # --- Provider inference ---
    model_patterns: list[str] = field(
        default_factory=list
    )  # Substrings to match model names

    # --- Auto-selection ---
    priority: int = 50  # Lower = preferred when multiple providers are configured

    # --- Testing ---
    test_protocol: str = "openai"  # "anthropic" | "openai" | "gemini" | "ollama"

    # --- Capability flags ---
    supports_reasoning_effort: bool = False


# ── Registry ────────────────────────────────────────────────────────

def normalize_openai_compatible_base_url(
    base_url: str,
    *,
    prefer_loopback_ip: bool = False,
) -> str:
    """Normalize an OpenAI-compatible endpoint URL for SDK/LiteLLM calls."""
    normalized = (base_url or "").strip().rstrip("/")
    if not normalized:
        return normalized
    if prefer_loopback_ip:
        normalized = normalized.replace("http://localhost:", "http://127.0.0.1:", 1)
        normalized = normalized.replace("https://localhost:", "https://127.0.0.1:", 1)
    if not normalized.endswith("/v1"):
        normalized = f"{normalized}/v1"
    return normalized


def _model_entries(raw_models: object) -> list[ModelEntry]:
    if not isinstance(raw_models, list):
        return []
    entries: list[ModelEntry] = []
    for item in raw_models:
        if isinstance(item, str) and item.strip():
            model_id = item.strip()
            entries.append(ModelEntry(id=model_id, name=model_id))
        elif isinstance(item, dict):
            model_id = str(item.get("id") or "").strip()
            if not model_id:
                continue
            entries.append(
                ModelEntry(
                    id=model_id,
                    name=str(item.get("name") or model_id),
                    context_window=item.get("context_window"),
                )
            )
    return entries


def parse_openai_compatible_profiles(raw: str | None) -> dict[str, ProviderConfig]:
    """Parse env-declared OpenAI-compatible endpoint profiles.

    This mirrors the deployment/profile style used by LiteLLM and other AI
    gateways: each named profile owns a base URL, optional API key, and model
    catalog while sharing the same OpenAI-compatible protocol adapter.
    """
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, list):
        return {}

    profiles: dict[str, ProviderConfig] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        profile_id = str(item.get("id") or "").strip().lower()
        if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,62}", profile_id):
            continue
        base_url = normalize_openai_compatible_base_url(
            str(item.get("base_url") or ""),
            prefer_loopback_ip=bool(item.get("prefer_loopback_ip")),
        )
        if not base_url:
            continue
        models = _model_entries(item.get("models"))
        default_model = str(item.get("default_model") or "").strip()
        if not default_model and models:
            default_model = models[0].id
        if not default_model:
            continue
        if not models:
            models = [ModelEntry(id=default_model, name=default_model)]
        profiles[profile_id] = ProviderConfig(
            default_model=default_model,
            prefix="openai/",
            base_url=base_url,
            label=str(item.get("label") or profile_id),
            credential_type="api_key_and_base_url",
            static_api_key=str(item.get("api_key") or ""),
            priority=int(item.get("priority") or 60),
            test_protocol="openai",
            models=models,
        )
    return profiles


_BASE_PROVIDER_REGISTRY: dict[str, ProviderConfig] = {
    "anthropic": ProviderConfig(
        default_model="claude-sonnet-4-6",
        prefix="anthropic/",
        label="Anthropic",
        credential_type="api_key",
        env_key_var="ANTHROPIC_API_KEY",
        model_patterns=["claude"],
        priority=10,
        test_protocol="anthropic",
        models=[
            ModelEntry(
                id="claude-sonnet-4-6", name="Claude Sonnet 4.6", context_window=200_000
            ),
            ModelEntry(
                id="claude-sonnet-4-5", name="Claude Sonnet 4.5", context_window=200_000
            ),
            ModelEntry(
                id="claude-haiku-4-5", name="Claude Haiku 4.5", context_window=200_000
            ),
        ],
    ),
    "openai": ProviderConfig(
        default_model="gpt-5.4",
        prefix="",
        label="OpenAI",
        credential_type="api_key_and_base_url",
        env_key_var="OPENAI_API_KEY",
        env_base_url_var="OPENAI_BASE_URL",
        model_patterns=["gpt", "o1", "o3"],
        priority=20,
        test_protocol="openai",
        supports_reasoning_effort=True,
        models=[
            ModelEntry(id="gpt-5.4", name="GPT-5.4", context_window=1_000_000),
            ModelEntry(id="gpt-5.4-pro", name="GPT-5.4 Pro", context_window=1_000_000),
            ModelEntry(
                id="gpt-5.4-mini", name="GPT-5.4 mini", context_window=1_000_000
            ),
            ModelEntry(id="gpt-5.4-nano", name="GPT-5.4 nano", context_window=400_000),
            ModelEntry(id="gpt-5.2", name="GPT-5.2", context_window=400_000),
            ModelEntry(id="gpt-5.2-pro", name="GPT-5.2 Pro", context_window=400_000),
            ModelEntry(id="gpt-5.1", name="GPT-5.1", context_window=400_000),
            ModelEntry(id="gpt-5-mini", name="GPT-5 mini", context_window=400_000),
            ModelEntry(
                id="gpt-5-chat-latest", name="GPT-5 Chat", context_window=128_000
            ),
        ],
    ),
    "gemini": ProviderConfig(
        default_model="gemini-3-flash-preview",
        prefix="gemini/",
        label="Google",
        credential_type="api_key",
        env_key_var="GEMINI_API_KEY",
        model_patterns=["gemini"],
        priority=15,
        test_protocol="gemini",
        models=[
            ModelEntry(
                id="gemini-3.1-pro-preview",
                name="Gemini 3.1 Pro Preview",
                context_window=1_000_000,
            ),
            ModelEntry(
                id="gemini-3-flash-preview",
                name="Gemini 3 Flash",
                context_window=1_000_000,
            ),
            ModelEntry(
                id="gemini-3.1-flash-lite-preview",
                name="Gemini 3.1 Flash-Lite Preview",
                context_window=1_000_000,
            ),
            ModelEntry(
                id="gemini-2.5-pro", name="Gemini 2.5 Pro", context_window=1_000_000
            ),
            ModelEntry(
                id="gemini-2.5-flash", name="Gemini 2.5 Flash", context_window=1_000_000
            ),
            ModelEntry(
                id="gemini-2.5-flash-lite",
                name="Gemini 2.5 Flash-Lite",
                context_window=1_000_000,
            ),
        ],
    ),
    "deepseek": ProviderConfig(
        default_model="deepseek-chat",
        prefix="deepseek/",
        label="DeepSeek",
        credential_type="api_key",
        env_key_var="DEEPSEEK_API_KEY",
        model_patterns=["deepseek"],
        priority=30,
        test_protocol="openai",
        models=[
            ModelEntry(
                id="deepseek-chat", name="DeepSeek V3.2", context_window=128_000
            ),
            ModelEntry(
                id="deepseek-reasoner",
                name="DeepSeek V3.2 Thinking",
                context_window=128_000,
            ),
        ],
    ),
    "xai": ProviderConfig(
        default_model="grok-4",
        prefix="xai/",
        base_url="https://api.x.ai/v1",
        label="xAI",
        credential_type="api_key",
        env_key_var="XAI_API_KEY",
        model_patterns=["grok"],
        priority=32,
        test_protocol="openai",
        models=[
            ModelEntry(id="grok-4", name="Grok 4", context_window=None),
            ModelEntry(id="grok-4-fast", name="Grok 4 Fast", context_window=None),
            ModelEntry(
                id="grok-4-1-fast-reasoning",
                name="Grok 4.1 Fast Reasoning",
                context_window=None,
            ),
            ModelEntry(
                id="grok-4.20-beta-latest-non-reasoning",
                name="Grok 4.20 Beta (Non-Reasoning)",
                context_window=None,
            ),
        ],
    ),
    "qwen": ProviderConfig(
        default_model="qwen3.6-plus",
        prefix="openai/",
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        label="Qwen",
        credential_type="api_key",
        env_key_var="QWEN_API_KEY",
        model_patterns=["qwen"],
        priority=35,
        test_protocol="openai",
        models=[
            ModelEntry(id="qwen3.6-plus", name="Qwen3.6 Plus", context_window=None),
            ModelEntry(
                id="qwen3-max-2026-01-23", name="Qwen3 Max", context_window=None
            ),
            ModelEntry(
                id="qwen3-coder-next", name="Qwen3 Coder Next", context_window=None
            ),
            ModelEntry(
                id="qwen3-coder-plus", name="Qwen3 Coder Plus", context_window=None
            ),
        ],
    ),
    "kimi": ProviderConfig(
        default_model="kimi-k2.5",
        prefix="openai/",
        base_url="https://api.moonshot.ai/v1",
        label="Kimi",
        credential_type="api_key",
        env_key_var="KIMI_API_KEY",
        model_patterns=["moonshot", "kimi"],
        priority=40,
        test_protocol="openai",
        models=[
            ModelEntry(id="kimi-k2.5", name="Kimi K2.5", context_window=256_000),
            ModelEntry(id="kimi-k2", name="Kimi K2", context_window=256_000),
            ModelEntry(
                id="kimi-k2-thinking", name="Kimi K2 Thinking", context_window=256_000
            ),
            ModelEntry(
                id="kimi-k2-turbo-preview",
                name="Kimi K2 Turbo Preview",
                context_window=256_000,
            ),
        ],
    ),
    "minimax": ProviderConfig(
        default_model="MiniMax-M2.7",
        prefix="openai/",
        base_url="https://api.minimax.io/v1",
        label="MiniMax",
        credential_type="api_key",
        env_key_var="MINIMAX_API_KEY",
        model_patterns=["minimax"],
        priority=45,
        test_protocol="openai",
        models=[
            ModelEntry(id="MiniMax-M2.7", name="MiniMax M2.7", context_window=204_800),
            ModelEntry(
                id="MiniMax-M2.7-highspeed",
                name="MiniMax M2.7 Highspeed",
                context_window=204_800,
            ),
            ModelEntry(id="MiniMax-M2.5", name="MiniMax M2.5", context_window=204_800),
            ModelEntry(
                id="MiniMax-M2.5-highspeed",
                name="MiniMax M2.5 Highspeed",
                context_window=204_800,
            ),
        ],
    ),
    "openrouter": ProviderConfig(
        default_model="anthropic/claude-sonnet-4-6",
        prefix="openrouter/",
        base_url="https://openrouter.ai/api/v1",
        label="OpenRouter",
        credential_type="api_key",
        env_key_var="OPENROUTER_API_KEY",
        model_patterns=[],  # Detected by "/" in model name, not by substring
        priority=90,
        test_protocol="openai",
        models=[
            ModelEntry(
                id="anthropic/claude-sonnet-4-6",
                name="Claude Sonnet 4.6 (OpenRouter)",
                context_window=200_000,
            ),
            ModelEntry(
                id="openai/gpt-5.4",
                name="GPT-5.4 (OpenRouter)",
                context_window=1_000_000,
            ),
            ModelEntry(
                id="xai/grok-4", name="Grok 4 (OpenRouter)", context_window=None
            ),
        ],
    ),
    "ollama": ProviderConfig(
        default_model="llama3.3",
        prefix="openai/",
        base_url="http://127.0.0.1:11434/v1",
        label="Ollama",
        credential_type="base_url_only",
        env_base_url_var="OLLAMA_BASE_URL",
        model_patterns=[],  # Fallback — unrecognized models go here
        priority=100,
        test_protocol="ollama",
        models=[
            ModelEntry(id="llama3.3", name="Llama 3.3", context_window=128_000),
            ModelEntry(id="qwen-2.5", name="Qwen 2.5", context_window=128_000),
        ],
    ),
}


def build_provider_registry() -> dict[str, ProviderConfig]:
    registry = dict(_BASE_PROVIDER_REGISTRY)
    for name, cfg in parse_openai_compatible_profiles(
        os.getenv("OPENAI_COMPATIBLE_PROVIDERS")
    ).items():
        if name not in registry:
            registry[name] = cfg
    return registry


PROVIDER_REGISTRY: dict[str, ProviderConfig] = build_provider_registry()


# ── Helpers ─────────────────────────────────────────────────────────


def litellm_model_name(provider: str, model: str) -> str:
    """Build the LiteLLM model identifier from provider + model name.

    Examples:
        ("anthropic", "claude-sonnet-4-6") → "anthropic/claude-sonnet-4-6"
        ("openai", "gpt-5.4") → "gpt-5.4"
        ("gemini", "gemini-2.5-flash") → "gemini/gemini-2.5-flash"
        ("xai", "grok-4") → "xai/grok-4"
        ("deepseek", "deepseek-chat") → "deepseek/deepseek-chat"
        ("openrouter", "anthropic/claude-sonnet-4-6") → "openrouter/anthropic/claude-sonnet-4-6"
    """
    cfg = PROVIDER_REGISTRY.get(provider)
    if not cfg:
        return model
    prefix = cfg.prefix
    # Avoid double-prefixing (e.g. user already passed "anthropic/claude-...")
    if prefix and model.startswith(prefix):
        return model
    return f"{prefix}{model}"


def infer_provider_from_model(model: str) -> str:
    """Infer provider from model name (data-driven via model_patterns).

    IMPORTANT: Check "/" first — OpenRouter models use "provider/model" format.
    "anthropic/claude-sonnet-4-6" must resolve to openrouter, not anthropic.
    """
    m = model.lower()
    if m.startswith("ollama/"):
        return "ollama"
    if "/" in m:
        return "openrouter"
    for name, cfg in PROVIDER_REGISTRY.items():
        for pattern in cfg.model_patterns:
            if pattern in m:
                return name
    return "ollama"
