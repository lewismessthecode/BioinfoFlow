from __future__ import annotations

from typing import Any

from app.services.llm.registry import get_provider_spec


def normalize_model_selection(
    selection: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not isinstance(selection, dict):
        return None

    model_id = str(selection.get("model_id") or "").strip()
    profile_id = str(selection.get("profile_id") or "").strip()
    if model_id:
        return {"model_id": model_id}
    if profile_id:
        return {"profile_id": profile_id}

    provider = str(selection.get("provider") or "").strip().lower()
    model = str(selection.get("model") or "").strip()
    if not model:
        return None
    if provider == "auto":
        provider = ""
    if not provider:
        return None
    return {"provider": provider, "model": model}


def known_model_supports_vision(
    selection: dict[str, Any] | None,
) -> bool | None:
    normalized = normalize_model_selection(selection)
    if not normalized or "provider" not in normalized:
        return None
    try:
        provider = get_provider_spec(normalized["provider"])
    except ValueError:
        return None
    model_id = normalized["model"]
    model = next((item for item in provider.bundled_models if item.id == model_id), None)
    return model.supports_vision if model is not None else None


def session_model_selection_from_metadata(
    metadata: dict[str, Any] | None,
) -> dict[str, str] | None:
    if not isinstance(metadata, dict):
        return None

    return normalize_model_selection(metadata.get("model_selection"))


def session_metadata_with_model_selection(
    metadata: dict[str, Any] | None,
    model_selection: dict[str, Any] | None,
) -> dict[str, Any] | None:
    next_metadata = dict(metadata or {})
    normalized = normalize_model_selection(model_selection)
    if normalized:
        next_metadata["model_selection"] = normalized
        return next_metadata

    next_metadata.pop("model_selection", None)
    return next_metadata or None
