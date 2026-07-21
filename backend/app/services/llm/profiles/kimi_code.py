from typing import Any

from app.services.llm.profiles.base import ProviderProfile
from app.services.llm.profiles.kimi_schema import normalize_kimi_tool_schema
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol


class KimiCodeProfile(ProviderProfile):
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
        thinking: dict[str, str] = {
            "type": "enabled" if reasoning.enabled else "disabled"
        }
        if model_name == "k3" and reasoning.enabled:
            thinking["effort"] = "low" if reasoning.effort == "low" else "high"
        compiled["extra_body"] = {
            **compiled.get("extra_body", {}),
            "thinking": thinking,
        }
        for tool in compiled.get("tools", []):
            function = tool.get("function") if isinstance(tool, dict) else None
            parameters = (
                function.get("parameters") if isinstance(function, dict) else None
            )
            if isinstance(parameters, dict):
                function["parameters"] = normalize_kimi_tool_schema(parameters)
        for message in compiled.get("messages", []):
            if (
                isinstance(message, dict)
                and message.get("role") == "assistant"
                and message.get("tool_calls")
                and message.get("content") in (None, "")
            ):
                message.pop("content", None)
        return compiled
