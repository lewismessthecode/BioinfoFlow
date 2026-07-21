from typing import Any

from app.services.llm.profiles.deepseek import DeepSeekProfile
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol

class KimiCodeProfile(DeepSeekProfile):
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
        max_tokens = compiled.pop("max_tokens", None)
        if max_tokens is not None:
            compiled["max_completion_tokens"] = max_tokens
        if reasoning.enabled:
            compiled["extra_body"] = {
                **compiled.get("extra_body", {}),
                "thinking": {"type": "enabled"},
            }
        return compiled
