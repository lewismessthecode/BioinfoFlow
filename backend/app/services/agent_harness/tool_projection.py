from __future__ import annotations

import json
import re
from pathlib import PurePath
from typing import Any

from app.services.agent_harness.contracts import (
    ToolExecutionMode,
    ToolPublicDetail,
    ToolProgressView,
)
from app.services.agent_harness.tools.specs import ToolSpec


_MAX_INPUT_SUMMARY_LENGTH = 200
_MAX_OUTPUT_SUMMARY_LENGTH = 300
_MAX_DETAIL_LENGTH = 4_000
_SENSITIVE_ASSIGNMENT = re.compile(
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL)[A-Z0-9_]*)=([^\s;&|]+)"
)
_SENSITIVE_FLAG = re.compile(
    r"(?i)(--?(?:api[-_]?key|access[-_]?token|token|secret|password|passwd|credential))(?:=|\s+)([^\s;&|]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)([^\s'\"]+)"
)
_URL_CREDENTIALS = re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@", re.I)
_SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?token|token|secret|password)=)([^&#\s]+)"
)


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
    public_details = public_tool_details(name, arguments)
    return ToolProgressView.model_validate(
        {
            "call_id": call_id,
            "group_id": group_id,
            "execution_mode": execution_mode,
            "name": name,
            "display_name": display_name,
            "category": category,
            "summary": summary,
            "arguments": {},
            "status": status,
            "revision": revision,
            "public_details": public_details,
        }
    )


def public_tool_details(
    name: str, arguments: dict[str, Any]
) -> list[ToolPublicDetail]:
    if name == "bash":
        details: list[ToolPublicDetail] = []
        command = arguments.get("command")
        if isinstance(command, str) and command.strip():
            value, truncated, redacted = _public_text(command, _MAX_DETAIL_LENGTH)
            details.append(
                ToolPublicDetail(
                    id="command",
                    kind="command",
                    value=value,
                    format="code",
                    copyable=not redacted,
                    truncated=truncated,
                    redacted=redacted,
                )
            )
        cwd = arguments.get("cwd")
        if isinstance(cwd, str) and cwd.strip():
            value, truncated = _public_path(cwd)
            details.append(
                ToolPublicDetail(
                    id="working-directory",
                    kind="working_directory",
                    value=value,
                    format="path",
                    copyable=not PurePath(cwd).is_absolute(),
                    truncated=truncated,
                    redacted=PurePath(cwd).is_absolute(),
                )
            )
        return details

    if name in {"read", "write", "edit"}:
        details = []
        path = arguments.get("path")
        if isinstance(path, str) and path.strip():
            value, truncated = _public_path(path)
            details.append(
                ToolPublicDetail(
                    id="path",
                    kind="path",
                    value=value,
                    format="path",
                    copyable=not PurePath(path).is_absolute(),
                    truncated=truncated,
                    redacted=PurePath(path).is_absolute(),
                )
            )
        if name == "read":
            range_parts = []
            if isinstance(arguments.get("offset"), int):
                range_parts.append(f"offset {arguments['offset']}")
            if isinstance(arguments.get("limit"), int):
                range_parts.append(f"limit {arguments['limit']}")
            if range_parts:
                details.append(
                    ToolPublicDetail(
                        id="input",
                        kind="input",
                        value=" · ".join(range_parts),
                    )
                )
        if name == "write" and isinstance(arguments.get("content"), str):
            details.append(
                ToolPublicDetail(
                    id="changes",
                    kind="changes",
                    value=f"{len(arguments['content'].encode('utf-8'))} bytes",
                )
            )
        if name == "edit":
            details.append(
                ToolPublicDetail(
                    id="changes",
                    kind="changes",
                    value=(
                        "Replace all matches"
                        if arguments.get("replace_all") is True
                        else "Replace one match"
                    ),
                )
            )
        return details

    return []


def public_output_summary(output: Any, *, tool_name: str | None = None) -> str | None:
    if output is None:
        return None
    if tool_name == "read" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else None
        start = output.get("start_line")
        end = output.get("end_line")
        if isinstance(start, int) and isinstance(end, int):
            text = f"Read lines {start}-{end}"
        else:
            text = "Read file"
        return f"{text} · {public_path}" if public_path else text
    if tool_name == "write" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else "file"
        byte_count = output.get("bytes_written")
        change = "updated" if output.get("changed") else "unchanged"
        suffix = f" · {byte_count} bytes" if isinstance(byte_count, int) else ""
        return _bounded_text(f"{public_path} {change}{suffix}", _MAX_OUTPUT_SUMMARY_LENGTH)
    if tool_name == "edit" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else "file"
        replacements = output.get("replacements")
        suffix = (
            f" · {replacements} replacements" if isinstance(replacements, int) else ""
        )
        return _bounded_text(f"{public_path} edited{suffix}", _MAX_OUTPUT_SUMMARY_LENGTH)
    if tool_name not in {None, "bash"}:
        return None
    if isinstance(output, str):
        text = output
    else:
        text = json.dumps(output, ensure_ascii=False, default=str)
    return _public_text(text, _MAX_OUTPUT_SUMMARY_LENGTH)[0]


def public_error_message(error: str | None) -> str | None:
    if not error:
        return None
    return _public_text(error, _MAX_OUTPUT_SUMMARY_LENGTH)[0]


def public_result_details(
    *, output_summary: str | None = None, error: str | None = None
) -> list[ToolPublicDetail]:
    details: list[ToolPublicDetail] = []
    if output_summary:
        value, truncated, redacted = _public_text(
            output_summary, _MAX_OUTPUT_SUMMARY_LENGTH
        )
        details.append(
            ToolPublicDetail(
                id="output",
                kind="output",
                value=value,
                format="code",
                copyable=not redacted,
                truncated=truncated,
                redacted=redacted,
            )
        )
    public_error = public_error_message(error)
    if public_error:
        details.append(
            ToolPublicDetail(
                id="error",
                kind="error",
                value=public_error,
                redacted=public_error != error,
            )
        )
    return details


def _input_summary(spec: ToolSpec, arguments: dict[str, Any]) -> str:
    values = [
        value
        for field in spec.input_summary_fields
        if (value := _summary_value(arguments.get(field))) is not None
    ]
    if not values:
        return spec.summary
    return _public_text(
        f"{spec.summary}: {' · '.join(values)}", _MAX_INPUT_SUMMARY_LENGTH
    )[0]


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


def _public_text(text: str, limit: int) -> tuple[str, bool, bool]:
    cleaned = "".join(character for character in text if character >= " " or character in "\n\t")
    redacted = _SENSITIVE_ASSIGNMENT.sub(r"\1=[REDACTED]", cleaned)
    redacted = _SENSITIVE_FLAG.sub(r"\1=[REDACTED]", redacted)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", redacted)
    redacted = _SENSITIVE_QUERY.sub(r"\1[REDACTED]", redacted)
    was_redacted = redacted != cleaned
    truncated = len(redacted) > limit
    return _bounded_text(redacted, limit), truncated, was_redacted


def _public_path(path: str) -> tuple[str, bool]:
    cleaned = " ".join(path.split())
    absolute = PurePath(cleaned).is_absolute()
    if absolute:
        parts = [part for part in PurePath(cleaned).parts if part not in {"/", ""}]
        cleaned = "…/" + "/".join(parts[-2:])
    truncated = len(cleaned) > _MAX_INPUT_SUMMARY_LENGTH
    return _bounded_text(cleaned, _MAX_INPUT_SUMMARY_LENGTH), truncated


__all__ = [
    "project_tool_view",
    "public_error_message",
    "public_output_summary",
    "public_result_details",
    "public_tool_details",
]
