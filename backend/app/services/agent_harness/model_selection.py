from __future__ import annotations

from typing import Any


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
