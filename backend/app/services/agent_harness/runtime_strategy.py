from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class RuntimeCapabilities:
    supports_streaming: bool = True
    supports_reasoning: bool = False
    supports_tools: bool = True
    supports_vision: bool = False

    def as_dict(self) -> dict[str, bool]:
        return {
            "supports_streaming": self.supports_streaming,
            "supports_reasoning": self.supports_reasoning,
            "supports_tools": self.supports_tools,
            "supports_vision": self.supports_vision,
        }


@dataclass(frozen=True)
class RuntimeStrategy:
    use_streaming: bool = True
    allow_thinking: bool = True
    allow_tools: bool = True
    max_tokens: int | None = None
    reasoning_effort: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "use_streaming": self.use_streaming,
            "allow_thinking": self.allow_thinking,
            "allow_tools": self.allow_tools,
            "max_tokens": self.max_tokens,
            "reasoning_effort": self.reasoning_effort,
        }


def capabilities_from_model(model) -> RuntimeCapabilities:
    return RuntimeCapabilities(
        supports_streaming=bool(getattr(model, "supports_streaming", True)),
        supports_reasoning=bool(getattr(model, "supports_reasoning", False)),
        supports_tools=bool(getattr(model, "supports_tools", True)),
        supports_vision=bool(getattr(model, "supports_vision", False)),
    )


def resolve_runtime_strategy(
    *,
    capabilities: RuntimeCapabilities,
    profile=None,
) -> RuntimeStrategy:
    prefer_streaming = (
        True if profile is None else bool(getattr(profile, "prefer_streaming", True))
    )
    allow_thinking = (
        True if profile is None else bool(getattr(profile, "allow_thinking", True))
    )
    allow_tools = (
        True if profile is None else bool(getattr(profile, "allow_tools", True))
    )
    return RuntimeStrategy(
        use_streaming=capabilities.supports_streaming and prefer_streaming,
        allow_thinking=capabilities.supports_reasoning and allow_thinking,
        allow_tools=capabilities.supports_tools and allow_tools,
        max_tokens=getattr(profile, "max_tokens", None)
        if profile is not None
        else None,
    )


def runtime_strategy_from_mapping(
    strategy: Mapping[str, Any] | None,
) -> RuntimeStrategy:
    if not isinstance(strategy, Mapping):
        return RuntimeStrategy()
    return RuntimeStrategy(
        use_streaming=bool(strategy.get("use_streaming", True)),
        allow_thinking=bool(strategy.get("allow_thinking", True)),
        allow_tools=bool(strategy.get("allow_tools", True)),
        max_tokens=_coerce_optional_int(strategy.get("max_tokens")),
        reasoning_effort=(
            strategy.get("reasoning_effort")
            if strategy.get("reasoning_effort") in {"low", "medium", "high"}
            else None
        ),
    )


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
