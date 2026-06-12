from __future__ import annotations

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

    for key, value in input.items():
        if key in properties:
            _validate_schema(value, properties[key], path=key)
    return dict(input)


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
