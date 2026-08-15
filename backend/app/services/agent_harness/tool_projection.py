from __future__ import annotations

import json
from typing import Any

from app.services.agent_harness.contracts import (
    ToolExecutionMode,
    ToolProgressView,
)
from app.services.agent_harness.tools.specs import ToolSpec


_MAX_INPUT_SUMMARY_LENGTH = 200
_MAX_OUTPUT_SUMMARY_LENGTH = 300


def project_tool_view(
    *,
    spec: ToolSpec | None,
    call_id: str,
    name: str,
    arguments: dict[str, Any],
    status: str,
    group_id: str,
    execution_mode: ToolExecutionMode,
    revision: int = 1,
) -> ToolProgressView:
    if spec is None:
        raise ValueError(f"registered tool metadata not found: {name}")
    display_name = spec.display_name
    category = spec.category
    summary = _input_summary(spec, arguments)
    return ToolProgressView.model_validate(
        {
            "call_id": call_id,
            "group_id": group_id,
            "execution_mode": execution_mode,
            "name": name,
            "display_name": display_name,
            "category": category,
            "summary": summary,
            "arguments": arguments,
            "status": status,
            "revision": revision,
        }
    )


def public_output_summary(output: Any) -> str | None:
    if output is None:
        return None
    if isinstance(output, str):
        text = output
    else:
        text = json.dumps(output, ensure_ascii=False, default=str)
    return _bounded_text(text, _MAX_OUTPUT_SUMMARY_LENGTH)


def _input_summary(spec: ToolSpec, arguments: dict[str, Any]) -> str:
    values = [
        value
        for field in spec.input_summary_fields
        if (value := _summary_value(arguments.get(field))) is not None
    ]
    if not values:
        return spec.summary
    return _bounded_text(
        f"{spec.summary}: {' · '.join(values)}", _MAX_INPUT_SUMMARY_LENGTH
    )


def _summary_value(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        text = " ".join(value.split())
    elif isinstance(value, (bool, int, float)):
        text = str(value)
    else:
        text = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return text or None


def _bounded_text(text: str, limit: int) -> str:
    return text if len(text) <= limit else f"{text[: limit - 3]}..."


__all__ = ["project_tool_view", "public_output_summary"]
