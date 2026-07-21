from __future__ import annotations

from dataclasses import dataclass

from app.services.llm.registry import ProviderSpec, provider_spec_for_kind


@dataclass(frozen=True)
class ProviderProfile:
    spec: ProviderSpec


def profile_for(provider_kind: str) -> ProviderProfile:
    spec = provider_spec_for_kind(provider_kind)
    if spec is None:
        raise ValueError(f"No provider profile for kind: {provider_kind}")
    return ProviderProfile(spec)
