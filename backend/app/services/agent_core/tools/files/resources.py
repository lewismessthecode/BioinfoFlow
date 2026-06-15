from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError


class ReadFileTool:
    spec = AgentToolSpec(
        name="files.read",
        description="Read a text file from an allowed workspace path.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "offset": {"type": "integer", "minimum": 0},
                "limit": {"type": "integer", "minimum": 1, "maximum": 2000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
                "line_count": {"type": "integer"},
            },
            "required": ["path", "content", "line_count"],
        },
        risk_level="read",
        read_scope=["workspace"],
        audit="Read a text file inside the allowed workspace.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        path = _resolve_path(input["path"], must_exist=True, allow_directory=False)
        content = path.read_text(encoding="utf-8")
        lines = content.splitlines()
        offset = int(input.get("offset") or 0)
        limit = int(input.get("limit") or 400)
        selected = lines[offset : offset + limit]
        return {
            "path": str(path),
            "content": "\n".join(selected),
            "line_count": len(lines),
        }


class WriteFileTool:
    spec = AgentToolSpec(
        name="files.write",
        description="Write a text file within an allowed workspace path.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "bytes_written": {"type": "integer"}},
            "required": ["path", "bytes_written"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Write a text file inside the allowed workspace.",
        rollback_hint="Restore the previous file contents from version control or overwrite the file again.",
        artifact_policy={"type": "file"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        path = _resolve_path_for_write(input["path"])
        content = input["content"]
        path.write_text(content, encoding="utf-8")
        return {"path": str(path), "bytes_written": len(content.encode("utf-8"))}


class EditFileTool:
    spec = AgentToolSpec(
        name="files.edit",
        description="Replace exact text in a file within an allowed workspace path.",
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}, "replacements": {"type": "integer"}},
            "required": ["path", "replacements"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Edit a text file inside the allowed workspace.",
        rollback_hint="Restore the previous file contents from version control or reverse the replacement.",
        artifact_policy={"type": "file"},
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        path = _resolve_path(input["path"], must_exist=True, allow_directory=False)
        content = path.read_text(encoding="utf-8")
        old_text = input["old_text"]
        new_text = input["new_text"]
        if old_text == new_text:
            raise BadRequestError("old_text and new_text must differ")
        replace_all = bool(input.get("replace_all", False))
        count = content.count(old_text)
        if count == 0:
            raise BadRequestError("old_text was not found in the file")
        if not replace_all and count != 1:
            raise BadRequestError("old_text must match exactly once unless replace_all is true")
        updated = content.replace(old_text, new_text) if replace_all else content.replace(old_text, new_text, 1)
        path.write_text(updated, encoding="utf-8")
        return {"path": str(path), "replacements": count if replace_all else 1}


def _resolve_path(raw_path: str | None, *, must_exist: bool, allow_directory: bool) -> Path:
    candidate = Path(raw_path or settings.repo_root)
    if not candidate.is_absolute():
        candidate = Path(settings.repo_root) / candidate
    return FilesystemPolicy().require_allowed_path(
        candidate,
        must_exist=must_exist,
        allow_directory=allow_directory,
    )


def _resolve_path_for_write(raw_path: str) -> Path:
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path(settings.repo_root) / candidate
    return FilesystemPolicy().require_parent_dir(candidate)
