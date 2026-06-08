from __future__ import annotations

from typing import Any

from app.utils.exceptions import BadRequestError


def normalize_tool_input(input: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(input, dict):
        raise BadRequestError("tool input must be an object")
    properties = schema.get("properties") or {}
    required = schema.get("required") or []
    additional = bool(schema.get("additionalProperties", True))

    missing = [key for key in required if key not in input]
    if missing:
        raise BadRequestError(f"missing required tool arguments: {', '.join(missing)}")

    if not additional:
        unknown = [key for key in input if key not in properties]
        if unknown:
            raise BadRequestError(f"unknown tool arguments: {', '.join(unknown)}")

    return dict(input)
