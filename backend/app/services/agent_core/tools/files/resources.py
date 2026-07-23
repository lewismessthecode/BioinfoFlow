from __future__ import annotations

import stat
from dataclasses import dataclass
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

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
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
            "properties": {
                "path": {"type": "string"},
                "bytes_written": {"type": "integer"},
            },
            "required": ["path", "bytes_written"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Write a text file inside the allowed workspace.",
        rollback_hint="Restore the previous file contents from version control or overwrite the file again.",
        artifact_policy={"type": "file"},
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
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
            "properties": {
                "path": {"type": "string"},
                "replacements": {"type": "integer"},
            },
            "required": ["path", "replacements"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Edit a text file inside the allowed workspace.",
        rollback_hint="Restore the previous file contents from version control or reverse the replacement.",
        artifact_policy={"type": "file"},
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
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
            raise BadRequestError(
                "old_text must match exactly once unless replace_all is true"
            )
        updated = (
            content.replace(old_text, new_text)
            if replace_all
            else content.replace(old_text, new_text, 1)
        )
        path.write_text(updated, encoding="utf-8")
        return {"path": str(path), "replacements": count if replace_all else 1}


class ApplyPatchTool:
    spec = AgentToolSpec(
        name="files.apply_patch",
        description=(
            "Apply a validated batch of create, exact-text replace, and delete "
            "operations to workspace files. Every path and replacement is checked "
            "before any file is changed. Use bash for rg, jq, and sed inspection; "
            "use this tool for structured file mutations."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "operations": {
                    "type": "array",
                    "minItems": 1,
                    "maxItems": 100,
                    "items": {
                        "oneOf": [
                            {
                                "type": "object",
                                "properties": {
                                    "op": {"const": "create"},
                                    "path": {"type": "string"},
                                    "content": {"type": "string"},
                                },
                                "required": ["op", "path", "content"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "op": {"const": "replace"},
                                    "path": {"type": "string"},
                                    "old_text": {"type": "string"},
                                    "new_text": {"type": "string"},
                                    "replace_all": {"type": "boolean"},
                                },
                                "required": ["op", "path", "old_text", "new_text"],
                                "additionalProperties": False,
                            },
                            {
                                "type": "object",
                                "properties": {
                                    "op": {"const": "delete"},
                                    "path": {"type": "string"},
                                },
                                "required": ["op", "path"],
                                "additionalProperties": False,
                            },
                        ]
                    },
                }
            },
            "required": ["operations"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"operations": {"type": "array"}},
            "required": ["operations"],
        },
        risk_level="act_high",
        read_scope=["workspace"],
        write_scope=["workspace"],
        audit="Apply a prevalidated batch of workspace file mutations.",
        rollback_hint="Restore affected files from version control or reverse the patch.",
        artifact_policy={"type": "file"},
    )

    async def run(
        self, input: dict[str, Any], context: AgentToolContext
    ) -> dict[str, Any]:
        del context
        operations = input.get("operations")
        if not isinstance(operations, list) or not operations:
            raise BadRequestError("operations must be a non-empty list")

        prepared: list[dict[str, Any]] = []
        seen_paths: set[Path] = set()
        for operation in operations:
            if not isinstance(operation, dict):
                raise BadRequestError("each operation must be an object")
            prepared_operation = _prepare_patch_operation(operation)
            path = prepared_operation["path"]
            if path in seen_paths:
                raise BadRequestError("multiple operations cannot target the same path")
            seen_paths.add(path)
            prepared.append(prepared_operation)

        summaries: list[dict[str, Any]] = []
        attempted: list[tuple[Path, _PatchTargetSnapshot]] = []
        try:
            for operation in prepared:
                op = operation["op"]
                path = operation["path"]
                attempted.append((path, _snapshot_patch_target(path)))
                if op == "create":
                    content = operation["content"]
                    path.write_text(content, encoding="utf-8")
                    summaries.append(
                        {
                            "op": op,
                            "path": str(path),
                            "bytes_written": len(content.encode("utf-8")),
                        }
                    )
                elif op == "replace":
                    path.write_text(operation["updated"], encoding="utf-8")
                    summaries.append(
                        {
                            "op": op,
                            "path": str(path),
                            "replacements": operation["replacements"],
                        }
                    )
                else:
                    path.unlink()
                    summaries.append({"op": op, "path": str(path)})
        except OSError as exc:
            rollback_errors = _restore_patch_targets(attempted)
            detail = f": {exc}"
            if rollback_errors:
                detail += f"; rollback errors: {'; '.join(rollback_errors)}"
            raise RuntimeError(f"file patch apply failed{detail}") from exc
        return {"operations": summaries}


def _prepare_patch_operation(operation: dict[str, Any]) -> dict[str, Any]:
    op = operation.get("op")
    if op == "create":
        path = _resolve_path_for_write(operation.get("path"))
        if path.exists():
            raise BadRequestError(f"file already exists: {path}")
        content = operation.get("content")
        if not isinstance(content, str):
            raise BadRequestError("create content must be text")
        return {"op": op, "path": path, "content": content}
    if op == "delete":
        path = _resolve_path(
            operation.get("path"), must_exist=True, allow_directory=False
        )
        return {"op": op, "path": path}
    if op != "replace":
        raise BadRequestError("operation op must be create, replace, or delete")

    path = _resolve_path(operation.get("path"), must_exist=True, allow_directory=False)
    content = path.read_text(encoding="utf-8")
    old_text = operation.get("old_text")
    new_text = operation.get("new_text")
    if not isinstance(old_text, str) or not isinstance(new_text, str):
        raise BadRequestError("replace old_text and new_text must be text")
    if old_text == new_text:
        raise BadRequestError("old_text and new_text must differ")
    count = content.count(old_text)
    if count == 0:
        raise BadRequestError("old_text was not found in the file")
    replace_all = bool(operation.get("replace_all", False))
    if not replace_all and count != 1:
        raise BadRequestError(
            "old_text must match exactly once unless replace_all is true"
        )
    replacements = count if replace_all else 1
    updated = (
        content.replace(old_text, new_text)
        if replace_all
        else content.replace(old_text, new_text, 1)
    )
    return {
        "op": op,
        "path": path,
        "updated": updated,
        "replacements": replacements,
    }


@dataclass(frozen=True, slots=True)
class _PatchTargetSnapshot:
    content: bytes | None
    mode: int | None


def _snapshot_patch_target(path: Path) -> _PatchTargetSnapshot:
    if not path.exists():
        return _PatchTargetSnapshot(content=None, mode=None)
    return _PatchTargetSnapshot(
        content=path.read_bytes(),
        mode=stat.S_IMODE(path.stat().st_mode),
    )


def _restore_patch_targets(
    attempted: list[tuple[Path, _PatchTargetSnapshot]],
) -> list[str]:
    errors: list[str] = []
    for path, original in reversed(attempted):
        try:
            if original.content is None:
                if path.exists():
                    path.unlink()
            else:
                path.write_bytes(original.content)
                if original.mode is not None:
                    path.chmod(original.mode)
        except OSError as exc:
            errors.append(f"{path}: {exc}")
    return errors


def _resolve_path(
    raw_path: str | None, *, must_exist: bool, allow_directory: bool
) -> Path:
    candidate = Path(raw_path or settings.repo_root)
    if not candidate.is_absolute():
        candidate = Path(settings.repo_root) / candidate
    return FilesystemPolicy().require_allowed_path(
        candidate,
        must_exist=must_exist,
        allow_directory=allow_directory,
    )


def _resolve_path_for_write(raw_path: str | None) -> Path:
    if not isinstance(raw_path, str) or not raw_path.strip():
        raise BadRequestError("path must be non-empty text")
    candidate = Path(raw_path)
    if not candidate.is_absolute():
        candidate = Path(settings.repo_root) / candidate
    return FilesystemPolicy().require_parent_dir(candidate)
