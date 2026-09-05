from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from app.services.agent_harness.contracts import AgentCommand, ENTRY_PAYLOAD_TYPES


async def build_user_message_payload(
    db: Any,
    session: Any,
    command: AgentCommand | dict[str, Any],
) -> dict[str, Any]:
    """Build the durable canonical user message outside the persistence seam."""

    raw = command if isinstance(command, dict) else command.model_dump(mode="json")
    raw_parts = raw.get("parts")
    if not isinstance(raw_parts, list) or not raw_parts:
        raise ValueError("message command requires parts")
    attachment_ids = [
        str(item.get("attachment_id"))
        for item in raw_parts
        if isinstance(item, dict)
        and item.get("type") in {"attachment_ref", "file_ref", "directory_ref"}
        and item.get("attachment_id") is not None
    ]
    from app.repositories.agent_harness_repo import AgentHarnessAttachmentRepository

    attachments = await AgentHarnessAttachmentRepository(db).require_ids_for_session(
        attachment_ids,
        session_id=str(session.id),
        workspace_id=str(session.workspace_id),
        user_id=session.user_id,
    )
    attachments_by_id = {str(item.id): item for item in attachments}
    command_id = str(raw.get("command_id") or "message")
    parts: list[dict[str, Any]] = []
    for index, item in enumerate(raw_parts):
        if not isinstance(item, dict):
            raise ValueError("message command parts must be objects")
        part_id = f"input:{command_id}:{index}"
        part_type = item.get("type")
        if part_type == "text":
            parts.append({"id": part_id, "type": "text", "text": item["text"]})
        elif part_type == "attachment_ref":
            attachment_id = str(item["attachment_id"])
            attachment = attachments_by_id[attachment_id]
            parts.append(
                {
                    "id": part_id,
                    "type": "attachment_ref",
                    "attachment_id": attachment_id,
                    "filename": attachment.filename,
                    "kind": attachment.kind,
                    "mime_type": attachment.mime_type,
                    "size_bytes": attachment.size_bytes,
                }
            )
        elif part_type in {"file_ref", "directory_ref"}:
            attachment_id = item.get("attachment_id")
            if attachment_id is not None:
                attachment = attachments_by_id[str(attachment_id)]
                parts.append(
                    {
                        "id": part_id,
                        "type": part_type,
                        "label": attachment.filename,
                        "attachment_id": str(attachment.id),
                    }
                )
            else:
                parts.append(
                    {
                        "id": part_id,
                        "type": part_type,
                        "label": str(item["path"]),
                        "project_id": item["project_id"],
                        "path": item["path"],
                    }
                )
        elif part_type == "workflow_ref":
            parts.append(
                {
                    "id": part_id,
                    "type": "workflow_ref",
                    "workflow_id": item["workflow_id"],
                    "label": str(item["workflow_id"]),
                    "project_id": item.get("project_id"),
                }
            )
        elif part_type == "run_ref":
            parts.append(
                {
                    "id": part_id,
                    "type": "run_ref",
                    "run_id": item["run_id"],
                    "label": str(item["run_id"]),
                }
            )
        else:
            raise ValueError(f"unsupported message part: {part_type}")
    return ENTRY_PAYLOAD_TYPES["message"].model_validate(
        {"role": "user", "parts": parts}
    ).model_dump(mode="json")


def user_message_payload_builder(
    db: Any,
) -> Callable[[Any, AgentCommand | dict[str, Any]], Awaitable[dict[str, Any]]]:
    async def build(session: Any, command: AgentCommand | dict[str, Any]):
        return await build_user_message_payload(db, session, command)

    return build


__all__ = ["build_user_message_payload", "user_message_payload_builder"]
