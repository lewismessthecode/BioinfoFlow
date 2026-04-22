"""Provider metadata endpoint — serves registry info to the frontend."""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.schemas.user_settings import ModelInfo
from app.services.agent.runtime.providers import PROVIDER_REGISTRY
from app.utils.responses import success_response

router = APIRouter(prefix="/providers", tags=["providers"])


@router.get("")
async def list_providers(request: Request):
    """Return metadata for all registered LLM providers."""
    result = []
    for name, cfg in PROVIDER_REGISTRY.items():
        credential_fields: list[str] = []
        if cfg.credential_type in {"api_key", "api_key_and_base_url"}:
            credential_fields.append("api_key")
        if cfg.credential_type in {"api_key_and_base_url", "base_url_only"}:
            credential_fields.append("base_url")
        if cfg.test_protocol == "ollama":
            credential_fields.append("model")

        result.append({
            "id": name,
            "label": cfg.label,
            "credential_type": cfg.credential_type,
            "credential_fields": credential_fields,
            "base_url": cfg.base_url or None,
            "default_model": cfg.default_model or None,
            "models": [
                ModelInfo(id=m.id, name=m.name, context_window=m.context_window).model_dump()
                for m in cfg.models
            ],
        })
    return success_response(result, request=request)
