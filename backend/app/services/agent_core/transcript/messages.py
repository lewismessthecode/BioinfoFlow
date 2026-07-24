from __future__ import annotations

import json
import base64
from dataclasses import dataclass
from typing import Any

from app.services.model_runtime.contracts import (
    ImagePart,
    InputPart,
    ModelTarget,
    ResponsesContinuation,
    TextPart,
    ToolCallPart,
    ToolResultPart,
)
from app.models.agent_core import AgentAttachmentStatus
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.services.agent_core.attachments import AgentAttachmentService
from app.utils.exceptions import NotFoundError


RESPONSES_CONTINUATION_METADATA_KEY = "_responses_continuation"


@dataclass(frozen=True)
class ResponsesContinuationAnchor:
    continuation: ResponsesContinuation
    turn_id: str | None


def text_part(text: str, *, phase: str | None = None) -> dict[str, str]:
    part = {"type": "text", "text": text}
    if phase is not None:
        part["phase"] = phase
    return part


def tool_calls_part(tool_calls: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "type": "tool_calls",
        "tool_calls": [
            normalized
            for tool_call in tool_calls
            if (normalized := _canonical_tool_call(tool_call)) is not None
        ],
    }


def parts_to_text(parts: list[dict[str, Any]] | None) -> str:
    text_parts: list[str] = []
    for part in parts or []:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            text_parts.append(part["text"])
    return "\n".join(text_parts).strip()


def provider_message_from_parts(
    role: str,
    parts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    text = parts_to_text(parts)
    if role == "assistant":
        tool_calls: list[dict[str, Any]] = []
        for part in parts:
            if part.get("type") == "tool_calls" and isinstance(part.get("tool_calls"), list):
                for raw_call in part["tool_calls"]:
                    canonical = _canonical_tool_call(raw_call)
                    if canonical is not None:
                        tool_calls.append(_provider_tool_call(canonical))
        message: dict[str, Any] = {"role": role, "content": text}
        if tool_calls:
            message["tool_calls"] = tool_calls
        return message
    if role == "tool":
        message = {"role": role, "content": text}
        tool_call_id = (metadata or {}).get("tool_call_id")
        if tool_call_id:
            message["tool_call_id"] = str(tool_call_id)
        if "is_error" in (metadata or {}):
            message["is_error"] = bool((metadata or {}).get("is_error"))
        return message
    return {"role": role, "content": text}


def model_input_parts_from_message(
    role: str,
    parts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
) -> tuple[InputPart, ...]:
    result: list[InputPart] = []
    if role == "user":
        text = parts_to_text(parts)
        if text:
            result.append(TextPart(text=text))
        return tuple(result)
    if role == "assistant":
        for part in parts:
            if part.get("type") != "text" or not isinstance(part.get("text"), str):
                continue
            text = part["text"]
            if not text:
                continue
            phase = part.get("phase")
            result.append(
                TextPart(
                    text=text,
                    phase=phase if phase in {"commentary", "final_answer"} else "final_answer",
                )
            )
        for part in parts:
            if part.get("type") != "tool_calls" or not isinstance(
                part.get("tool_calls"), list
            ):
                continue
            for raw_call in part["tool_calls"]:
                canonical = _canonical_tool_call(raw_call)
                if canonical is None:
                    continue
                result.append(
                    ToolCallPart(
                        call_id=canonical["id"],
                        name=canonical["name"],
                        arguments=canonical["arguments"],
                    )
                )
        return tuple(result)
    if role == "tool":
        text = parts_to_text(parts)
        result.append(
            ToolResultPart(
                call_id=str((metadata or {}).get("tool_call_id") or ""),
                output=text,
                is_error=bool((metadata or {}).get("is_error", False)),
            )
        )
    return tuple(result)


async def model_input_parts_from_message_async(
    role: str,
    parts: list[dict[str, Any]],
    metadata: dict[str, Any] | None = None,
    *,
    db,
    session_id: str,
    workspace_id: str,
    user_id: str,
) -> tuple[InputPart, ...]:
    if role != "user":
        return model_input_parts_from_message(role, parts, metadata)
    result: list[InputPart] = []
    attachments = AgentAttachmentRepository(db)
    attachment_service = AgentAttachmentService(db)
    for part in parts:
        if part.get("type") == "text" and isinstance(part.get("text"), str):
            if part["text"]:
                result.append(TextPart(text=part["text"]))
            continue
        if part.get("type") != "image_ref":
            continue
        attachment_id = part.get("attachment_id")
        if not isinstance(attachment_id, str):
            raise NotFoundError("Attachment not found")
        attachment = await attachments.get_owned(
            attachment_id,
            session_id=session_id,
            workspace_id=workspace_id,
            user_id=user_id,
        )
        stored_metadata = attachment.attachment_metadata if attachment else {}
        if (
            attachment is None
            or attachment.status != AgentAttachmentStatus.READY
            or attachment.kind != "image"
            or stored_metadata.get("sha256") != part.get("sha256")
        ):
            raise NotFoundError("Attachment not found")
        model_relpath = stored_metadata.get("model_relpath")
        model_mime_type = stored_metadata.get("model_mime_type")
        if not isinstance(model_relpath, str) or not isinstance(
            model_mime_type, str
        ):
            raise NotFoundError("Attachment image metadata is invalid")
        model_path = attachment_service.validated_root(attachment) / model_relpath
        if not model_path.is_file() or model_path.is_symlink():
            raise NotFoundError("Attachment image is not available")
        detail = part.get("detail")
        result.append(
            ImagePart(
                mime_type=model_mime_type,
                data=base64.b64encode(model_path.read_bytes()).decode("ascii"),
                sha256=stored_metadata["sha256"],
                detail=(
                    detail
                    if detail in {"auto", "low", "high", "original"}
                    else None
                ),
            )
        )
    return tuple(result)


def metadata_with_responses_continuation(
    metadata: dict[str, Any] | None,
    continuation: ResponsesContinuation | None,
) -> dict[str, Any] | None:
    result = dict(metadata or {})
    if continuation is None or continuation.target is None:
        return result or None
    result[RESPONSES_CONTINUATION_METADATA_KEY] = continuation.to_private_dict()
    return result


def responses_continuation_from_metadata(
    metadata: dict[str, Any] | None,
) -> ResponsesContinuation | None:
    if not isinstance(metadata, dict):
        return None
    return ResponsesContinuation.from_private_dict(
        metadata.get(RESPONSES_CONTINUATION_METADATA_KEY)
    )


def latest_responses_continuation(
    messages: list[Any],
    *,
    turn_id: str | None = None,
    target: ModelTarget | None = None,
) -> ResponsesContinuation | None:
    anchor = latest_responses_continuation_anchor(
        messages,
        turn_id=turn_id,
        target=target,
    )
    return anchor.continuation if anchor is not None else None


def latest_responses_continuation_anchor(
    messages: list[Any],
    *,
    turn_id: str | None = None,
    target: ModelTarget | None = None,
) -> ResponsesContinuationAnchor | None:
    for message in reversed(messages):
        message_turn_id = getattr(message, "turn_id", None)
        if turn_id is not None and str(message_turn_id or "") != turn_id:
            continue
        if getattr(message, "status", None) != "committed":
            continue
        continuation = responses_continuation_from_metadata(
            getattr(message, "message_metadata", None)
        )
        if continuation is not None and (
            target is None or continuation.matches_target(target)
        ):
            return ResponsesContinuationAnchor(
                continuation=continuation,
                turn_id=str(message_turn_id) if message_turn_id is not None else None,
            )
    return None


def _canonical_tool_call(raw_call: Any) -> dict[str, Any] | None:
    if not isinstance(raw_call, dict):
        return None
    function = raw_call.get("function")
    if isinstance(function, dict):
        name = function.get("name")
        arguments = function.get("arguments")
    else:
        name = raw_call.get("name")
        arguments = raw_call.get("arguments")
    if not isinstance(name, str) or not name:
        return None
    return {
        "id": str(raw_call.get("id") or ""),
        "name": name,
        "arguments": _tool_arguments(arguments),
    }


def _provider_tool_call(canonical: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": canonical["id"],
        "type": "function",
        "function": {
            "name": canonical["name"],
            "arguments": json.dumps(
                canonical["arguments"],
                separators=(",", ":"),
                default=str,
            ),
        },
    }


def _tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if not isinstance(value, str):
        return {}
    try:
        parsed = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}
