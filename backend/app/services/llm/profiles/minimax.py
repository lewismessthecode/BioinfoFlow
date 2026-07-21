from typing import Any

from app.services.llm.profiles.base import ProviderProfile
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol


class MiniMaxProfile(ProviderProfile):
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
        if not reasoning.enabled:
            return compiled
        extra_body: dict[str, Any] = {
            **compiled.get("extra_body", {}),
            "reasoning_split": True,
        }
        if model_name.lower() == "minimax-m3":
            extra_body["thinking"] = {"type": "adaptive"}
        compiled["extra_body"] = extra_body
        return compiled
