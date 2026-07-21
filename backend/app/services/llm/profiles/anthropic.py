from __future__ import annotations

from typing import Any

from app.services.llm.profiles.base import (
    CatalogRequest,
    ProviderConnection,
    ProviderProfile,
)
from app.services.llm.registry import ModelSpec


class AnthropicProfile(ProviderProfile):
    def catalog_request(self, connection: ProviderConnection) -> CatalogRequest:
        request = super().catalog_request(connection)
        assert request is not None
        return CatalogRequest(
            url=request.url,
            headers={**request.headers, "anthropic-version": "2023-06-01"},
        )

    def parse_catalog(self, payload: dict[str, Any]) -> tuple[ModelSpec, ...]:
        items = payload.get("data")
        if not isinstance(items, list):
            return ()
        return tuple(
            ModelSpec(
                item["id"],
                item.get("display_name") or item["id"],
            )
            for item in items
            if isinstance(item, dict) and isinstance(item.get("id"), str)
        )
