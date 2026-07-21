from __future__ import annotations

from typing import Any

from app.services.llm.profiles.base import ProviderProfile
from app.services.llm.registry import ModelSpec


class GeminiProfile(ProviderProfile):
    def parse_catalog(self, payload: dict[str, Any]) -> tuple[ModelSpec, ...]:
        items = payload.get("models")
        if not isinstance(items, list):
            return ()
        models = []
        for item in items:
            if not isinstance(item, dict) or not isinstance(item.get("name"), str):
                continue
            model_id = item["name"].removeprefix("models/")
            models.append(
                ModelSpec(model_id, item.get("displayName") or model_id)
            )
        return tuple(models)
