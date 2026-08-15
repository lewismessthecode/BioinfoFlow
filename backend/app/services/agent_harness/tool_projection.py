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
    r"(?i)\b([A-Z0-9_]*(?:API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?ID)?|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE[_-]?KEY)[A-Z0-9_]*)\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s;&|]+)"
)
_SENSITIVE_FLAG = re.compile(
    r"(?i)(--?(?:api[-_]?key|access[-_]?key|access[-_]?token|token|secret|password|passwd|credential))(?:=|\s+)(?:\"[^\"]*\"|'[^']*'|[^\s;&|]+)"
)
_AUTHORIZATION = re.compile(
    r"(?i)(authorization\s*:\s*(?:bearer|basic)\s+)(?:\"[^\"]*\"|'[^']*'|[^\s'\"]+)"
)
_SENSITIVE_HEADER = re.compile(
    r"(?i)((?:x-api-key|api-key|x-auth-token|x-access-token)\s*:\s*)(?:\"[^\"]*\"|'[^']*'|[^\s'\"]+)"
)
_SENSITIVE_MAPPING = re.compile(
    r"(?i)((?:\"|')?[A-Z0-9_-]*(?:API[_-]?KEY|ACCESS[_-]?KEY(?:[_-]?ID)?|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|PRIVATE[_-]?KEY)[A-Z0-9_-]*(?:\"|')?\s*:\s*)(?:\"[^\"]*\"|'[^']*'|[^\s,;}]+)"
)
_URL_CREDENTIALS = re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@", re.I)
_SENSITIVE_QUERY = re.compile(
    r"(?i)([?&](?:api[_-]?key|access[_-]?key|access[_-]?token|token|secret|password)=)([^&#\s]+)"
)
_FILE_URL_PATH = re.compile(r"(file://)(/[^\s'\";&|<>`$()]*)", re.I)
_KNOWN_SECRET = re.compile(
    r"(?<![A-Za-z0-9_])(?:"
    r"sk-[A-Za-z0-9_-]{8,}|"
    r"gh[pousr]_[A-Za-z0-9]{12,}|"
    r"github_pat_[A-Za-z0-9_]{12,}|"
    r"(?:AKIA|ASIA)[0-9A-Z]{12,}|"
    r"AIza[0-9A-Za-z_-]{20,}|"
    r"xox[baprs]-[A-Za-z0-9-]{10,}"
    r")"
)
_UNIX_ABSOLUTE_PATH = re.compile(r"(?<![A-Za-z0-9_:/\\…])/(?:[^\s'\";&|<>`$()]+)")
_BASH_RESULT_SUMMARY = re.compile(
    r"(?:exit_code=-?\d+(?: · truncated=true)?|truncated=true)"
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


def public_tool_details(name: str, arguments: dict[str, Any]) -> list[ToolPublicDetail]:
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
            redacted = value != " ".join(cwd.split())
            details.append(
                ToolPublicDetail(
                    id="working-directory",
                    kind="working_directory",
                    value=value,
                    format="path",
                    copyable=not redacted,
                    truncated=truncated,
                    redacted=redacted,
                )
            )
        return details

    if name in {"read", "write", "edit"}:
        details = []
        path = arguments.get("path")
        if isinstance(path, str) and path.strip():
            value, truncated = _public_path(path)
            redacted = value != " ".join(path.split())
            details.append(
                ToolPublicDetail(
                    id="path",
                    kind="path",
                    value=value,
                    format="path",
                    copyable=not redacted,
                    truncated=truncated,
                    redacted=redacted,
                )
            )
        if name == "read":
            range_parts = []
            if isinstance(arguments.get("offset"), int):
                range_parts.append(f"offset={arguments['offset']}")
            if isinstance(arguments.get("limit"), int):
                range_parts.append(f"limit={arguments['limit']}")
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
                    value=f"bytes={len(arguments['content'].encode('utf-8'))}",
                )
            )
        if name == "edit":
            details.append(
                ToolPublicDetail(
                    id="changes",
                    kind="changes",
                    value=f"replace_all={str(arguments.get('replace_all') is True).lower()}",
                )
            )
        return details

    return []


def public_output_summary(output: Any, *, tool_name: str | None = None) -> str | None:
    if output is None:
        return None
    if tool_name == "bash":
        if not isinstance(output, dict):
            return None
        values: list[str] = []
        exit_code = output.get("exit_code")
        if isinstance(exit_code, int) and not isinstance(exit_code, bool):
            values.append(f"exit_code={exit_code}")
        if any(
            output.get(field) is True
            for field in ("truncated", "stdout_truncated", "stderr_truncated")
        ):
            values.append("truncated=true")
        return " · ".join(values) or None
    if tool_name == "read" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else None
        start = output.get("start_line")
        end = output.get("end_line")
        if isinstance(start, int) and isinstance(end, int):
            text = f"start_line={start} · end_line={end}"
        else:
            text = None
        values = [text, f"path={public_path}" if public_path else None]
        return " · ".join(value for value in values if value) or None
    if tool_name == "write" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else None
        byte_count = output.get("bytes_written")
        values = [
            f"path={public_path}" if public_path else None,
            f"changed={str(bool(output.get('changed'))).lower()}",
            f"bytes={byte_count}" if isinstance(byte_count, int) else None,
        ]
        return _bounded_text(
            " · ".join(value for value in values if value),
            _MAX_OUTPUT_SUMMARY_LENGTH,
        )
    if tool_name == "edit" and isinstance(output, dict):
        path = output.get("path")
        public_path = _public_path(path)[0] if isinstance(path, str) else None
        replacements = output.get("replacements")
        values = [
            f"path={public_path}" if public_path else None,
            f"replacements={replacements}" if isinstance(replacements, int) else None,
        ]
        return _bounded_text(
            " · ".join(value for value in values if value),
            _MAX_OUTPUT_SUMMARY_LENGTH,
        )
    return None


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


def public_tool_progress_view(value: Any) -> ToolProgressView:
    """Rebuild persisted tool progress through the public contract boundary."""

    raw = dict(value) if isinstance(value, dict) else {}
    name = str(raw.get("name") or "unknown")
    arguments = raw.get("arguments")
    arguments = arguments if isinstance(arguments, dict) else {}
    summary = _public_text(
        str(raw.get("summary") or raw.get("display_name") or name),
        _MAX_INPUT_SUMMARY_LENGTH,
    )[0]
    input_summary = (
        _public_text(str(raw["input_summary"]), _MAX_INPUT_SUMMARY_LENGTH)[0]
        if raw.get("input_summary")
        else None
    )
    raw_output_summary = (
        str(raw["output_summary"]) if raw.get("output_summary") else None
    )
    output_summary = (
        _public_bash_result_summary(raw_output_summary)
        if name == "bash"
        else (
            _public_text(raw_output_summary, _MAX_OUTPUT_SUMMARY_LENGTH)[0]
            if raw_output_summary
            else None
        )
    )
    error = public_error_message(str(raw["error"])) if raw.get("error") else None

    persisted_details = _public_detail_list(raw.get("public_details"))
    if arguments:
        input_details = public_tool_details(name, arguments)
    else:
        input_details = [
            detail
            for detail in persisted_details
            if detail.kind not in {"output", "error"}
        ]
    result_details = public_result_details(
        output_summary=output_summary,
        error=error,
    )
    if output_summary is None and name != "bash":
        result_details.extend(
            detail for detail in persisted_details if detail.kind == "output"
        )
    if error is None:
        result_details.extend(
            detail for detail in persisted_details if detail.kind == "error"
        )

    return ToolProgressView.model_validate(
        {
            "call_id": str(raw.get("call_id") or "unknown"),
            "group_id": str(raw.get("group_id") or "unknown"),
            "execution_mode": raw.get("execution_mode") or "serial",
            "name": name,
            "display_name": str(raw.get("display_name") or name),
            "category": raw.get("category") or "other",
            "summary": summary,
            "arguments": {},
            "status": raw.get("status") or "pending",
            "revision": int(raw.get("revision") or 0),
            "started_at": raw.get("started_at"),
            "completed_at": raw.get("completed_at"),
            "input_summary": input_summary,
            "output_summary": output_summary,
            "error": error,
            "public_details": [*input_details, *result_details],
        }
    )


def public_detail_list(value: Any) -> list[ToolPublicDetail]:
    return _public_detail_list(value)


def _input_summary(spec: ToolSpec, arguments: dict[str, Any]) -> str:
    values = [
        value
        for field in spec.input_summary_fields
        if (value := _summary_value(arguments.get(field))) is not None
    ]
    if not values:
        return spec.display_name
    return _public_text(
        f"{spec.display_name}: {' · '.join(values)}", _MAX_INPUT_SUMMARY_LENGTH
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


def _public_bash_result_summary(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = " ".join(value.split())
    return cleaned if _BASH_RESULT_SUMMARY.fullmatch(cleaned) else None


def _public_text(text: str, limit: int) -> tuple[str, bool, bool]:
    cleaned = "".join(
        character for character in text if character >= " " or character in "\n\t"
    )
    redacted = _SENSITIVE_ASSIGNMENT.sub(r"\1=[REDACTED]", cleaned)
    redacted = _SENSITIVE_FLAG.sub(r"\1=[REDACTED]", redacted)
    redacted = _AUTHORIZATION.sub(r"\1[REDACTED]", redacted)
    redacted = _SENSITIVE_HEADER.sub(r"\1[REDACTED]", redacted)
    redacted = _SENSITIVE_MAPPING.sub(r"\1[REDACTED]", redacted)
    redacted = _URL_CREDENTIALS.sub(r"\1[REDACTED]@", redacted)
    redacted = _SENSITIVE_QUERY.sub(r"\1[REDACTED]", redacted)
    redacted = _KNOWN_SECRET.sub("[REDACTED]", redacted)
    redacted = _FILE_URL_PATH.sub(
        lambda match: f"{match.group(1)}{_public_path(match.group(2))[0]}", redacted
    )
    redacted = _UNIX_ABSOLUTE_PATH.sub(
        lambda match: _public_path(match.group(0))[0], redacted
    )
    was_redacted = redacted != cleaned
    truncated = len(redacted) > limit
    return _bounded_text(redacted, limit), truncated, was_redacted


def _public_path(path: str) -> tuple[str, bool]:
    cleaned = " ".join(path.split())
    cleaned = _SENSITIVE_ASSIGNMENT.sub(r"\1=[REDACTED]", cleaned)
    cleaned = _KNOWN_SECRET.sub("[REDACTED]", cleaned)
    absolute = PurePath(cleaned).is_absolute()
    if absolute:
        parts = [part for part in PurePath(cleaned).parts if part not in {"/", ""}]
        cleaned = "…/" + "/".join(parts[-2:])
    truncated = len(cleaned) > _MAX_INPUT_SUMMARY_LENGTH
    return _bounded_text(cleaned, _MAX_INPUT_SUMMARY_LENGTH), truncated


def _public_detail_list(value: Any) -> list[ToolPublicDetail]:
    details: list[ToolPublicDetail] = []
    for raw in value if isinstance(value, list) else []:
        if not isinstance(raw, dict):
            continue
        kind = raw.get("kind")
        if kind not in {
            "command",
            "working_directory",
            "path",
            "input",
            "output",
            "changes",
            "error",
            "metadata",
        }:
            continue
        original = str(raw.get("value") or "")
        if kind in {"working_directory", "path"}:
            public_value, truncated = _public_path(original)
            redacted = public_value != original
        else:
            public_value, truncated, redacted = _public_text(
                original, _MAX_DETAIL_LENGTH
            )
        if not public_value:
            continue
        label = raw.get("label")
        public_label = (
            _public_text(str(label), _MAX_INPUT_SUMMARY_LENGTH)[0]
            if label is not None
            else None
        )
        details.append(
            ToolPublicDetail(
                id=str(raw.get("id") or kind),
                kind=kind,
                label=public_label,
                value=public_value,
                format=raw.get("format")
                if raw.get("format") in {"text", "code", "path", "json", "diff"}
                else "text",
                copyable=bool(raw.get("copyable")) and not redacted and not truncated,
                truncated=bool(raw.get("truncated")) or truncated,
                redacted=bool(raw.get("redacted")) or redacted,
            )
        )
    return details


__all__ = [
    "project_tool_view",
    "public_detail_list",
    "public_error_message",
    "public_output_summary",
    "public_result_details",
    "public_tool_progress_view",
    "public_tool_details",
]
