from __future__ import annotations

from typing import Any

from app.services.llm.profiles.base import ProviderProfile
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol


class QwenProfile(ProviderProfile):
    def compile_request(
        self,
        request: dict[str, Any],
        *,
        model_name: str,
        wire_protocol: WireProtocol,
        reasoning: ReasoningRequest,
    ) -> dict[str, Any]:
        compiled = super().compile_request(
            request,
            model_name=model_name,
            wire_protocol=wire_protocol,
            reasoning=ReasoningRequest(enabled=False),
        )
        if "qwen" not in model_name.lower():
            return compiled
        compiled["extra_body"] = {
            **compiled.get("extra_body", {}),
            "enable_thinking": reasoning.enabled,
        }
        return compiled
