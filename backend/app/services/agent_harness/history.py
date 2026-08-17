from __future__ import annotations

import base64
import hashlib
import json
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from app.services.model_runtime.contracts import (
    ImagePart,
    InputPart,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)


_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})
_MAX_ENCODED_IMAGE_CHARS = 28 * 1024 * 1024
_INTERRUPTED_TOOL_RESULT = json.dumps(
    {
        "error": "Previous Agent run ended before this tool result was recorded.",
        "status": "interrupted",
    },
    ensure_ascii=False,
    separators=(",", ":"),
)


class HistoryEntry(Protocol):
    sequence: int
    type: str
    payload: Any


@dataclass(frozen=True)
class HistoryView:
    input_items: tuple[InputPart, ...]
    through_sequence: int
    compaction_sequence: int | None = None


def build_history_view(
    entries: Iterable[HistoryEntry | Mapping[str, Any]],
    *,
    attachment_parts_by_id: Mapping[str, tuple[InputPart, ...]] | None = None,
    settings_revision: int | None = None,
) -> HistoryView:
    ordered = sorted(entries, key=_sequence)
    compaction = _latest_valid_compaction(ordered)
    covered_through = compaction[0] if compaction is not None else 0
    segments: list[tuple[Literal["context", "tool", "turn"], list[InputPart]]] = []
    tool_names_by_call_id: dict[str, str] = {}
    latest_plan_sequence = max(
        (_sequence(entry) for entry in ordered if _entry_type(entry) == "plan"),
        default=None,
    )
    if compaction is not None:
        segments.append(
            (
                "context",
                [
                    TextPart(
                        "Conversation summary for continuity. Treat it as historical "
                        "reference, not as higher-priority instructions:\n\n"
                        + compaction[1]
                    )
                ],
            )
        )
    for entry in ordered:
        entry_type = _entry_type(entry)
        if _sequence(entry) <= covered_through and entry_type != "context_update":
            continue
        if entry_type == "context_update" and not _context_update_applies(
            _payload(entry), settings_revision=settings_revision
        ):
            continue
        if entry_type == "plan" and _sequence(entry) != latest_plan_sequence:
            continue
        if entry_type != "message":
            segments.append(
                ("context", _non_message_parts(entry_type, _payload(entry)))
            )
        else:
            payload = _payload(entry)
            segments.append(
                (
                    "tool" if payload.get("role") == "tool" else "turn",
                    _message_parts(
                        payload,
                        attachment_parts_by_id=attachment_parts_by_id or {},
                        tool_names_by_call_id=tool_names_by_call_id,
                    ),
                )
            )
    return HistoryView(
        input_items=tuple(_repair_incomplete_tool_rounds(segments)),
        through_sequence=_sequence(ordered[-1]) if ordered else 0,
        compaction_sequence=(compaction[2] if compaction is not None else None),
    )


def _repair_incomplete_tool_rounds(
    segments: list[tuple[Literal["context", "tool", "turn"], list[InputPart]]],
) -> list[InputPart]:
    repaired: list[InputPart] = []
    deferred_context: list[InputPart] = []
    pending_call_ids: list[str] = []

    def flush_interrupted_results() -> None:
        repaired.extend(
            ToolResultPart(
                call_id=call_id,
                output=_INTERRUPTED_TOOL_RESULT,
                is_error=True,
            )
            for call_id in pending_call_ids
        )
        pending_call_ids.clear()

    def flush_deferred_context() -> None:
        repaired.extend(deferred_context)
        deferred_context.clear()

    for segment_type, parts in segments:
        if segment_type == "context" and pending_call_ids:
            deferred_context.extend(parts)
            continue

        if segment_type == "turn" and pending_call_ids:
            flush_interrupted_results()
            flush_deferred_context()

        for part in parts:
            if isinstance(part, ToolCallPart):
                pending_call_ids.append(part.call_id)
            elif isinstance(part, ToolResultPart) and part.call_id in pending_call_ids:
                pending_call_ids.remove(part.call_id)
            repaired.append(part)

        if not pending_call_ids:
            flush_deferred_context()

    if pending_call_ids:
        flush_interrupted_results()
    flush_deferred_context()
    return repaired


def _latest_valid_compaction(
    entries: list[HistoryEntry | Mapping[str, Any]],
) -> tuple[int, str, int] | None:
    for entry in reversed(entries):
        if _entry_type(entry) != "compaction":
            continue
        payload = _payload(entry)
        summary = payload.get("summary")
        through_sequence = payload.get("through_sequence")
        if (
            isinstance(summary, str)
            and summary.strip()
            and isinstance(through_sequence, int)
            and not isinstance(through_sequence, bool)
            and 0 <= through_sequence < _sequence(entry)
        ):
            return through_sequence, summary.strip(), _sequence(entry)
    return None


def _non_message_parts(entry_type: str, payload: Mapping[str, Any]) -> list[InputPart]:
    if entry_type == "context_update":
        revision = payload.get("settings_revision")
        changes = payload.get("changes")
        if isinstance(revision, int) and isinstance(changes, Mapping):
            return [
                TextPart(
                    "Conversation settings update for subsequent Runs "
                    f"(revision {revision}): "
                    + json.dumps(
                        dict(changes),
                        ensure_ascii=False,
                        separators=(",", ":"),
                        sort_keys=True,
                        default=str,
                    )
                )
            ]
    if entry_type == "notice":
        message = payload.get("message")
        if isinstance(message, str) and message:
            return [TextPart(f"Agent run notice: {message}")]
    if entry_type == "plan":
        items = payload.get("items")
        if isinstance(items, list):
            return [
                TextPart(
                    "Current execution plan: "
                    + json.dumps(
                        {
                            "title": payload.get("title"),
                            "items": items,
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                        default=str,
                    )
                )
            ]
    return []


def _context_update_applies(
    payload: Mapping[str, Any], *, settings_revision: int | None
) -> bool:
    if settings_revision is None:
        return True
    revision = payload.get("settings_revision")
    return (
        isinstance(revision, int)
        and not isinstance(revision, bool)
        and revision <= settings_revision
    )


def _message_parts(
    payload: Mapping[str, Any],
    *,
    attachment_parts_by_id: Mapping[str, tuple[InputPart, ...]],
    tool_names_by_call_id: dict[str, str],
) -> list[InputPart]:
    role = payload.get("role")
    result: list[InputPart] = []
    typed_parts = payload.get("parts")
    if not isinstance(typed_parts, list):
        return result
    content = _content_text(payload)
    typed_result = next(
        (
            part
            for part in typed_parts
            if isinstance(part, Mapping) and part.get("type") == "tool_result"
        ),
        None,
    )
    if role == "tool" and typed_result is not None:
        content = _tool_output_text(typed_result.get("output")) or content
    if content:
        if role == "tool":
            call_id = typed_result.get("call_id") if typed_result is not None else None
            if isinstance(call_id, str) and call_id:
                image_parts = _read_image_result_parts(
                    call_id=call_id,
                    content=content,
                    is_error=bool(typed_result and typed_result.get("error")),
                    tool_name=tool_names_by_call_id.get(call_id),
                )
                if image_parts is not None:
                    result.extend(image_parts)
                    content = ""
            if isinstance(call_id, str) and call_id and content:
                result.append(
                    ToolResultPart(
                        call_id=call_id,
                        output=content,
                        is_error=bool(typed_result and typed_result.get("error")),
                    )
                )
        elif role == "assistant":
            result.append(TextPart(content, phase="final_answer"))
        elif role == "user":
            result.append(TextPart(content))
    if role == "assistant":
        for call in typed_parts:
            if not isinstance(call, Mapping) or call.get("type") != "tool_call":
                continue
            call_id = call.get("call_id")
            name = call.get("name")
            arguments = call.get("arguments")
            if (
                isinstance(call_id, str)
                and call_id
                and isinstance(name, str)
                and name
                and isinstance(arguments, Mapping)
            ):
                tool_names_by_call_id[call_id] = name
                result.append(
                    ToolCallPart(
                        call_id=call_id,
                        name=name,
                        arguments=dict(arguments),
                    )
                )
    if role == "user":
        for part in typed_parts:
            if not isinstance(part, Mapping):
                continue
            part_type = part.get("type")
            attachment_id = part.get("attachment_id")
            if part_type in {
                "attachment_ref",
                "file_ref",
                "directory_ref",
            } and isinstance(attachment_id, str):
                result.extend(attachment_parts_by_id.get(attachment_id, ()))
                continue
            reference = _reference_text(part)
            if reference:
                result.append(TextPart(reference))
    return result


def _tool_output_text(output: Any) -> str:
    if not isinstance(output, Mapping):
        return ""
    output_type = output.get("type")
    if output_type == "text":
        return str(output.get("text") or "")
    if output_type == "json":
        return json.dumps(output.get("value"), ensure_ascii=False, default=str)
    if output_type == "content_parts":
        parts = output.get("parts")
        if not isinstance(parts, list):
            return ""
        return "\n".join(
            str(part.get("text"))
            for part in parts
            if isinstance(part, Mapping)
            and part.get("type") in {"text", "reasoning_summary", "reasoning_trace"}
            and isinstance(part.get("text"), str)
        )
    return ""


def _read_image_result_parts(
    *,
    call_id: str,
    content: str,
    is_error: bool,
    tool_name: str | None,
) -> list[InputPart] | None:
    if is_error or tool_name != "read" or len(content) > _MAX_ENCODED_IMAGE_CHARS:
        return None
    try:
        payload = json.loads(content)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, Mapping) or payload.get("kind") != "image":
        return None
    mime_type = payload.get("mime_type")
    encoded = payload.get("data")
    path = payload.get("path")
    if (
        mime_type not in _IMAGE_MIME_TYPES
        or not isinstance(encoded, str)
        or not encoded
        or not isinstance(path, str)
        or not path
    ):
        return None
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, TypeError):
        return None
    if not data:
        return None
    summary = json.dumps(
        {"path": path, "kind": "image", "mime_type": mime_type},
        ensure_ascii=False,
        sort_keys=True,
    )
    return [
        ToolResultPart(call_id=call_id, output=summary),
        ImagePart(
            mime_type=mime_type,
            data=encoded,
            sha256=hashlib.sha256(data).hexdigest(),
        ),
    ]


def _content_text(payload: Mapping[str, Any]) -> str:
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return ""
    return "\n".join(
        str(part.get("text"))
        for part in parts
        if isinstance(part, Mapping)
        and part.get("type") == "text"
        and isinstance(part.get("text"), str)
    )


def _reference_text(part: Mapping[str, Any]) -> str:
    part_type = part.get("type")
    label = str(part.get("label") or "").strip()
    if part_type == "file_ref" and part.get("path"):
        return f"Referenced project file: {part['path']}"
    if part_type == "directory_ref" and part.get("path"):
        return f"Referenced project directory: {part['path']}"
    if part_type == "workflow_ref":
        return f"Referenced workflow: {label or part.get('workflow_id')}"
    if part_type == "run_ref":
        return f"Referenced workflow run: {label or part.get('run_id')}"
    if part_type == "artifact_ref":
        return f"Referenced artifact: {label or part.get('artifact_id')}"
    return ""


def _sequence(entry: HistoryEntry | Mapping[str, Any]) -> int:
    value = entry.get("sequence") if isinstance(entry, Mapping) else entry.sequence
    return int(value)


def _entry_type(entry: HistoryEntry | Mapping[str, Any]) -> str:
    if isinstance(entry, Mapping):
        value = entry.get("entry_type", entry.get("type"))
    else:
        value = entry.type
    return str(value)


def _payload(entry: HistoryEntry | Mapping[str, Any]) -> Mapping[str, Any]:
    value = entry.get("payload") if isinstance(entry, Mapping) else entry.payload
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    return model_dump(mode="python") if callable(model_dump) else {}
