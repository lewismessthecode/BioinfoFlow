from __future__ import annotations

from typing import Any

from app.services.llm.profiles.base import (
    CatalogRequest,
    ProviderConnection,
    ProviderProfile,
)
from app.services.llm.registry import ModelSpec


class GeminiProfile(ProviderProfile):
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
