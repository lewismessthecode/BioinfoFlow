from __future__ import annotations

from pathlib import PurePosixPath
from typing import Any

from app.models.agent_core import AgentAttachmentStatus
from app.path_layout import safe_join
from app.repositories.agent_core_repo import AgentAttachmentRepository
from app.services.agent_core.attachments import AgentAttachmentService
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError, NotFoundError


class AttachmentSearchTool:
    spec = AgentToolSpec(
        name="attachments.search",
        description=(
            "Search or list paths in one uploaded folder attachment. Returns a "
            "bounded manifest view without recursively injecting file contents."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string"},
                "query": {"type": "string", "maxLength": 500},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
            "required": ["attachment_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string"},
                "matches": {"type": "array"},
                "truncated": {"type": "boolean"},
            },
            "required": ["attachment_id", "matches", "truncated"],
        },
        risk_level="read",
        read_scope=["agent_session_attachments"],
        audit="Search the current session's uploaded folder manifest.",
        parallel_safe=True,
    )

    async def run(
        self,
        input: dict[str, Any],
        context: AgentToolContext,
    ) -> dict[str, Any]:
        attachment = await _owned_attachment(input, context)
        if attachment.kind != "folder":
            raise BadRequestError("attachments.search requires a folder attachment")
        query = str(input.get("query") or "").casefold()
        limit = min(max(int(input.get("limit") or 50), 1), 100)
        manifest = [
            path
            for path in (attachment.attachment_metadata or {}).get("manifest", [])
            if isinstance(path, str) and (not query or query in path.casefold())
        ]
        selected = manifest[:limit]
        return {
            "attachment_id": str(attachment.id),
            "matches": [{"path": path} for path in selected],
            "truncated": len(manifest) > len(selected),
        }


class AttachmentReadTool:
    spec = AgentToolSpec(
        name="attachments.read",
        description=(
            "Read bounded UTF-8 text from an uploaded file or a manifest-listed "
            "file inside an uploaded folder."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string"},
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["attachment_id"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "attachment_id": {"type": "string"},
                "path": {"type": "string"},
                "content": {"type": "string"},
                "line_count": {"type": "integer"},
            },
            "required": ["attachment_id", "path", "content", "line_count"],
        },
        risk_level="read",
        read_scope=["agent_session_attachments"],
        audit="Read bounded text from the current session's uploaded attachments.",
        parallel_safe=True,
    )

    async def run(
        self,
        input: dict[str, Any],
        context: AgentToolContext,
    ) -> dict[str, Any]:
        attachment = await _owned_attachment(input, context)
        metadata = attachment.attachment_metadata or {}
        root = AgentAttachmentService(context.db).validated_root(attachment)
        requested_path = input.get("path")
        if attachment.kind == "folder":
            if not isinstance(requested_path, str) or not requested_path.strip():
                raise BadRequestError("Folder attachments require a file path")
            normalized = _normalized_manifest_path(requested_path)
            manifest = metadata.get("manifest") or []
            if normalized not in manifest:
                raise NotFoundError("Attachment file not found")
            files_relpath = metadata.get("files_relpath")
            if not isinstance(files_relpath, str):
                raise NotFoundError("Attachment folder metadata is invalid")
            files_root = safe_join(
                root,
                files_relpath,
                escape_message="Attachment folder escapes its root",
            )
            target = safe_join(
                files_root,
                normalized,
                escape_message="Attachment file escapes its root",
            )
            display_path = normalized
        else:
            if requested_path not in {None, ""}:
                raise BadRequestError("Standalone attachments do not accept a path")
            original_relpath = metadata.get("preview_relpath")
            if not isinstance(original_relpath, str):
                raise NotFoundError("Attachment file metadata is invalid")
            target = safe_join(
                root,
                original_relpath,
                escape_message="Attachment file escapes its root",
            )
            display_path = attachment.filename
        if not target.is_file() or target.is_symlink():
            raise NotFoundError("Attachment file not found")
        try:
            content = target.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise BadRequestError("Attachment file is not valid UTF-8 text") from exc
        lines = content.splitlines()
        offset = max(int(input.get("offset") or 0), 0)
        limit = min(max(int(input.get("limit") or 400), 1), 2000)
        return {
            "attachment_id": str(attachment.id),
            "path": display_path,
            "content": "\n".join(lines[offset : offset + limit]),
            "line_count": len(lines),
        }


async def _owned_attachment(input: dict[str, Any], context: AgentToolContext):
    attachment_id = input.get("attachment_id")
    if not isinstance(attachment_id, str) or not attachment_id:
        raise BadRequestError("attachment_id is required")
    attachment = await AgentAttachmentRepository(context.db).get_owned(
        attachment_id,
        session_id=context.session_id,
        workspace_id=context.workspace_id,
        user_id=context.user_id,
    )
    if attachment is None or attachment.status != AgentAttachmentStatus.READY:
        raise NotFoundError("Attachment not found")
    return attachment


def _normalized_manifest_path(path: str) -> str:
    if not path or path.startswith("/") or "\\" in path or "//" in path:
        raise BadRequestError("Attachment path is invalid")
    candidate = PurePosixPath(path)
    if any(part in {"", ".", ".."} for part in candidate.parts):
        raise BadRequestError("Attachment path is invalid")
    return candidate.as_posix()
