from __future__ import annotations

from typing import Any

from litellm.utils import get_supported_openai_params

from app.services.llm.profiles.base import (
    CatalogRequest,
    ProviderConnection,
    ProviderProfile,
)
from app.services.llm.registry import ModelSpec
from app.services.model_runtime.contracts import ReasoningRequest, WireProtocol


class GeminiProfile(ProviderProfile):
    def compile_request(
        self,
        request: dict[str, Any],
        *,
        model_name: str,
        wire_protocol: WireProtocol,
        reasoning: ReasoningRequest,
    ) -> dict[str, Any]:
        if not reasoning.enabled:
            return super().compile_request(
                request,
                model_name=model_name,
                wire_protocol=wire_protocol,
                reasoning=ReasoningRequest(enabled=False),
            )

        supported = set(
            get_supported_openai_params(
                model=model_name,
                custom_llm_provider="gemini",
            )
        )
        if wire_protocol == "responses":
            if "reasoning" not in supported:
                reasoning = ReasoningRequest(enabled=False)
        elif "reasoning_effort" not in supported:
            reasoning = ReasoningRequest(enabled=False)

        return super().compile_request(
            request,
            model_name=model_name,
            wire_protocol=wire_protocol,
            reasoning=reasoning,
        )

    def catalog_request(self, connection: ProviderConnection) -> CatalogRequest:
        request = super().catalog_request(connection)
        assert request is not None
        return CatalogRequest(
            url=request.url,
            headers=request.headers,
            params={"pageSize": 1000},
        )

    def parse_catalog(self, payload: dict[str, Any]) -> tuple[ModelSpec, ...]:
        items = payload.get("models")
        if not isinstance(items, list):
            return ()
        models = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            methods = item.get("supportedGenerationMethods")
            if isinstance(methods, list) and "generateContent" not in methods:
                continue
            model_id = item["name"].removeprefix("models/")
            models.append(
                ModelSpec(
                    model_id,
                    item.get("displayName") or model_id,
                    context_length=item.get("inputTokenLimit"),
                    max_output_tokens=item.get("outputTokenLimit"),
                )
            )
        return tuple(models)
