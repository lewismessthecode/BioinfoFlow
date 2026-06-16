from __future__ import annotations

import json
from typing import Any

from app.utils.exceptions import BadRequestError


_TYPE_MAP = {
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "object": dict,
    "array": list,
}


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

    normalized = dict(input)
    for key, value in input.items():
        if key in properties:
            normalized[key] = _coerce_schema_value(value, properties[key])
            _validate_schema(normalized[key], properties[key], path=key)
    return normalized


def validate_tool_output(output: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(output, dict):
        raise BadRequestError("tool output must be an object")
    _validate_schema(output, schema, path="output")
    return output


def _validate_schema(value: Any, schema: dict[str, Any], *, path: str) -> None:
    expected_type = schema.get("type")
    if expected_type:
        python_type = _TYPE_MAP.get(str(expected_type))
        if python_type is not None and not isinstance(value, python_type):
            raise BadRequestError(f"{path} must be {expected_type}")
    if isinstance(value, bool) and schema.get("type") in {"integer", "number"}:
        raise BadRequestError(f"{path} must be {schema.get('type')}")
    enum_values = schema.get("enum")
    if isinstance(enum_values, list) and enum_values and value not in enum_values:
        allowed = ", ".join(str(item) for item in enum_values)
        raise BadRequestError(f"{path} must be one of: {allowed}")
    if isinstance(value, str):
        min_length = schema.get("minLength")
        max_length = schema.get("maxLength")
        if min_length is not None and len(value) < int(min_length):
            raise BadRequestError(f"{path} must have length >= {min_length}")
        if max_length is not None and len(value) > int(max_length):
            raise BadRequestError(f"{path} must have length <= {max_length}")
    if isinstance(value, int):
        minimum = schema.get("minimum")
        maximum = schema.get("maximum")
        if minimum is not None and value < minimum:
            raise BadRequestError(f"{path} must be >= {minimum}")
        if maximum is not None and value > maximum:
            raise BadRequestError(f"{path} must be <= {maximum}")
    if isinstance(value, dict):
        properties = schema.get("properties") or {}
        required = schema.get("required") or []
        additional = bool(schema.get("additionalProperties", True))
        missing = [key for key in required if key not in value]
        if missing:
            raise BadRequestError(f"{path} is missing required keys: {', '.join(missing)}")
        if not additional:
            unknown = [key for key in value if key not in properties]
            if unknown:
                raise BadRequestError(f"{path} has unknown keys: {', '.join(unknown)}")
        for key, item in value.items():
            if key in properties:
                _validate_schema(item, properties[key], path=f"{path}.{key}")
        return
    if isinstance(value, list):
        item_schema = schema.get("items") or {}
        for index, item in enumerate(value):
            _validate_schema(item, item_schema, path=f"{path}[{index}]")


def _coerce_schema_value(value: Any, schema: dict[str, Any]) -> Any:
    expected_type = str(schema.get("type") or "")
    if expected_type == "integer" and isinstance(value, str):
        stripped = value.strip()
        if stripped and stripped.lstrip("-").isdigit():
            return int(stripped)
    if expected_type == "number" and isinstance(value, str):
        stripped = value.strip()
        try:
            return float(stripped)
        except ValueError:
            return value
    if expected_type == "boolean" and isinstance(value, str):
        lowered = value.strip().lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False
    if expected_type in {"object", "array"} and isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return value
        try:
            parsed = json.loads(stripped)
        except json.JSONDecodeError:
            return value
        if expected_type == "object" and isinstance(parsed, dict):
            return parsed
        if expected_type == "array" and isinstance(parsed, list):
            return parsed
    return value
