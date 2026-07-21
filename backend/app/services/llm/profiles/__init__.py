from __future__ import annotations

from app.services.llm.profiles.anthropic import AnthropicProfile
from app.services.llm.profiles.base import (
    CatalogRequest,
    ProviderConnection,
    ProviderProfile,
)
from app.services.llm.profiles.deepseek import DeepSeekProfile
from app.services.llm.profiles.gemini import GeminiProfile
from app.services.llm.profiles.kimi_code import KimiCodeProfile
from app.services.llm.profiles.minimax import MiniMaxProfile
from app.services.llm.profiles.openrouter import OpenRouterProfile
from app.services.llm.profiles.zai import ZaiProfile
from app.services.llm.registry import provider_spec_for_kind


_PROFILE_TYPES = {
    "anthropic": AnthropicProfile,
    "deepseek": DeepSeekProfile,
    "openrouter": OpenRouterProfile,
    "gemini": GeminiProfile,
    "minimax": MiniMaxProfile,
    "kimi_code": KimiCodeProfile,
    "zai": ZaiProfile,
}


def profile_for(provider_kind: str) -> ProviderProfile:
    spec = provider_spec_for_kind(provider_kind)
    if spec is None:
        raise ValueError(f"No provider profile for kind: {provider_kind}")
    profile_type = _PROFILE_TYPES.get(provider_kind, ProviderProfile)
    return profile_type(spec)


__all__ = [
    "CatalogRequest",
    "ProviderConnection",
    "ProviderProfile",
    "profile_for",
]
