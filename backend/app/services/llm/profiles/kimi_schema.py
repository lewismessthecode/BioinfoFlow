from __future__ import annotations

import copy
from typing import Any


_SCHEMA_MAP_KEYS = (
    "$defs",
    "definitions",
    "dependentSchemas",
    "patternProperties",
    "properties",
)
_SCHEMA_SINGLE_KEYS = (
    "additionalItems",
    "additionalProperties",
    "contains",
    "contentSchema",
    "else",
    "if",
    "not",
    "propertyNames",
    "then",
    "unevaluatedItems",
    "unevaluatedProperties",
)
_SCHEMA_ARRAY_KEYS = ("allOf", "anyOf", "oneOf", "prefixItems")
_TYPE_INFERENCE_SKIP_KEYS = {
    "$ref",
    "allOf",
    "anyOf",
    "else",
    "if",
    "not",
    "oneOf",
    "then",
}


def normalize_kimi_tool_schema(schema: dict[str, Any]) -> dict[str, Any]:
    root = copy.deepcopy(schema)
    resolved = _resolve_node(root, root, set())
    if not isinstance(resolved, dict):
        raise ValueError("JSON Schema root must be an object")
    for bucket in ("$defs", "definitions"):
        if not _contains_definition_ref(resolved, bucket):
            resolved.pop(bucket, None)
    _complete_types(resolved)
    return resolved


def _resolve_node(node: Any, root: dict[str, Any], visiting: set[str]) -> Any:
    if isinstance(node, list):
        return [_resolve_node(item, root, visiting) for item in node]
    if not isinstance(node, dict):
        return node

    ref = node.get("$ref")
    if isinstance(ref, str) and (ref == "#" or ref.startswith("#/")):
        if ref in visiting:
            return copy.deepcopy(node)
        found, target = _resolve_pointer(root, ref)
        if found:
            resolved = _resolve_node(target, root, visiting | {ref})
            if isinstance(resolved, dict):
                merged = dict(resolved)
                merged.update(
                    {
                        key: _resolve_node(value, root, visiting)
                        for key, value in node.items()
                        if key != "$ref"
                    }
                )
                return merged
            return resolved

    return {key: _resolve_node(value, root, visiting) for key, value in node.items()}


def _resolve_pointer(root: dict[str, Any], ref: str) -> tuple[bool, Any]:
    if ref == "#":
        return True, root
    current: Any = root
    for raw_part in ref[2:].split("/"):
        part = raw_part.replace("~1", "/").replace("~0", "~")
        if isinstance(current, dict) and part in current:
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index < len(current):
                current = current[index]
                continue
        return False, None
    return True, current


def _contains_definition_ref(node: Any, bucket: str) -> bool:
    if isinstance(node, list):
        return any(_contains_definition_ref(item, bucket) for item in node)
    if not isinstance(node, dict):
        return False
    ref = node.get("$ref")
    if isinstance(ref, str) and ref.startswith(f"#/{bucket}/"):
        return True
    return any(
        _contains_definition_ref(value, bucket)
        for key, value in node.items()
        if key != bucket
    )


def _complete_types(schema: dict[str, Any]) -> None:
    if "type" not in schema and not (_TYPE_INFERENCE_SKIP_KEYS & schema.keys()):
        inferred = _infer_type(schema)
        if inferred is not None:
            schema["type"] = inferred

    for key in _SCHEMA_MAP_KEYS:
        value = schema.get(key)
        if isinstance(value, dict):
            for child in value.values():
                if isinstance(child, dict):
                    _complete_types(child)
    for key in _SCHEMA_SINGLE_KEYS:
        value = schema.get(key)
        if isinstance(value, dict):
            _complete_types(value)
    for key in _SCHEMA_ARRAY_KEYS:
        value = schema.get(key)
        if isinstance(value, list):
            for child in value:
                if isinstance(child, dict):
                    _complete_types(child)
    items = schema.get("items")
    if isinstance(items, dict):
        _complete_types(items)
    elif isinstance(items, list):
        for child in items:
            if isinstance(child, dict):
                _complete_types(child)


def _infer_type(schema: dict[str, Any]) -> str | list[str] | None:
    enum = schema.get("enum")
    if isinstance(enum, list) and enum:
        return _infer_value_types(enum)
    if "const" in schema:
        return _infer_value_types([schema["const"]])
    if any(
        key in schema
        for key in (
            "properties",
            "required",
            "additionalProperties",
            "minProperties",
            "maxProperties",
        )
    ):
        return "object"
    if any(key in schema for key in ("items", "prefixItems", "minItems", "maxItems")):
        return "array"
    if any(key in schema for key in ("minLength", "maxLength", "pattern", "format")):
        return "string"
    if any(
        key in schema
        for key in (
            "minimum",
            "maximum",
            "exclusiveMinimum",
            "exclusiveMaximum",
            "multipleOf",
        )
    ):
        return "number"
    return None


def _infer_value_types(values: list[Any]) -> str | list[str]:
    types = []
    for value in values:
        value_type = _json_type(value)
        if value_type not in types:
            types.append(value_type)
    return types[0] if len(types) == 1 else types


def _json_type(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, int):
        return "integer"
    if isinstance(value, float):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    raise ValueError(f"Unsupported JSON Schema value: {value!r}")
