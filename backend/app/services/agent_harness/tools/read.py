from __future__ import annotations

import base64
import codecs
import mimetypes
from typing import Any

from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


_DEFAULT_LINES = 200
_MAX_LINES = 2_000
_MAX_TEXT_BYTES = 8 * 1024 * 1024
_MAX_IMAGE_BYTES = 20 * 1024 * 1024
_IMAGE_MIME_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp"})


class ReadTool:
    spec = ToolSpec(
        name="read",
        description=(
            "Read a file in the workspace. Text is returned with line numbers and "
            "pagination; supported images are returned as base64 multimodal content."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "offset": {"type": "integer", "minimum": 1},
                "limit": {"type": "integer", "minimum": 1, "maximum": _MAX_LINES},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        replay_policy="safe",
        display_name="Read",
        category="read",
        summary="Read file",
        input_summary_fields=("path",),
        path_argument="path",
        target_scoped=True,
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        raw_path = arguments.get("path")
        mime_type = mimetypes.guess_type(str(raw_path))[0] or "application/octet-stream"
        is_image = mime_type in _IMAGE_MIME_TYPES
        try:
            file_read = await context.backend.read_file(
                raw_path,
                max_bytes=_MAX_IMAGE_BYTES if is_image else _MAX_TEXT_BYTES,
                allow_truncated=not is_image,
            )
        except ValueError as exc:
            if is_image and str(exc) == "file exceeds the configured read limit":
                raise ValueError("image exceeds the 20 MiB read limit") from None
            raise
        path = file_read.path
        data = file_read.data
        if is_image:
            return {
                "path": path,
                "kind": "image",
                "mime_type": mime_type,
                "data": base64.b64encode(data).decode("ascii"),
            }
        if _looks_binary(data):
            raise ValueError(
                "binary or domain data file; inspect it with an appropriate command-line program"
            )
        decoder = codecs.getincrementaldecoder("utf-8")()
        text = decoder.decode(data, final=not file_read.truncated)
        lines = text.splitlines()
        offset = _positive_int(arguments.get("offset"), default=1, maximum=None)
        limit = _positive_int(
            arguments.get("limit"), default=_DEFAULT_LINES, maximum=_MAX_LINES
        )
        start = offset - 1
        if file_read.truncated and start >= len(lines):
            raise ValueError(
                "offset is beyond the bounded read window; use bash with an appropriate command-line program"
            )
        selected = lines[start : start + limit]
        end_line = start + len(selected)
        has_more = end_line < len(lines) or file_read.truncated
        next_offset = end_line + 1 if has_more else None
        return {
            "path": path,
            "kind": "text",
            "text": "\n".join(
                f"{line_number}: {line}"
                for line_number, line in enumerate(selected, start=offset)
            ),
            "start_line": offset,
            "end_line": end_line,
            "total_lines": None if file_read.truncated else len(lines),
            "next_offset": next_offset,
            "truncated": has_more,
        }


def _looks_binary(data: bytes) -> bool:
    return b"\x00" in data[:8192]


def _positive_int(value: Any, *, default: int, maximum: int | None) -> int:
    if value is None:
        return default
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise ValueError("offset and limit must be positive integers")
    if maximum is not None and value > maximum:
        raise ValueError(f"limit must not exceed {maximum}")
    return value
