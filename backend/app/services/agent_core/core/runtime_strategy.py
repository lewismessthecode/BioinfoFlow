from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeCapabilities:
    supports_streaming: bool = True
    supports_reasoning: bool = False
    supports_tools: bool = True

    def as_dict(self) -> dict[str, bool]:
        return {
            "supports_streaming": self.supports_streaming,
            "supports_reasoning": self.supports_reasoning,
            "supports_tools": self.supports_tools,
        }


@dataclass(frozen=True)
class RuntimeStrategy:
    use_streaming: bool = True
    allow_thinking: bool = True
    allow_tools: bool = True
    max_tokens: int | None = None
    reasoning_budget: int | None = None
    fallback_model_ids: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "use_streaming": self.use_streaming,
            "allow_thinking": self.allow_thinking,
            "allow_tools": self.allow_tools,
            "max_tokens": self.max_tokens,
            "reasoning_budget": self.reasoning_budget,
            "fallback_model_ids": list(self.fallback_model_ids),
        }


def capabilities_from_model(model) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        supports_streaming=bool(getattr(model, "supports_streaming", True)),
        supports_reasoning=bool(getattr(model, "supports_reasoning", False)),
        supports_tools=bool(getattr(model, "supports_tools", True)),
    )


def resolve_runtime_strategy(
    *,
    capabilities: RuntimeCapabilities,
    profile=None,
) -> RuntimeStrategy:
    prefer_streaming = True if profile is None else bool(getattr(profile, "prefer_streaming", True))
    allow_thinking = True if profile is None else bool(getattr(profile, "allow_thinking", True))
    allow_tools = True if profile is None else bool(getattr(profile, "allow_tools", True))
    fallback_model_ids = tuple(str(item) for item in (getattr(profile, "fallback_model_ids", None) or ()))
    return RuntimeStrategy(
        use_streaming=capabilities.supports_streaming and prefer_streaming,
        allow_thinking=capabilities.supports_reasoning and allow_thinking,
        allow_tools=capabilities.supports_tools and allow_tools,
        max_tokens=getattr(profile, "max_tokens", None) if profile is not None else None,
        reasoning_budget=getattr(profile, "reasoning_budget", None) if profile is not None else None,
        fallback_model_ids=fallback_model_ids,
    )
