from __future__ import annotations

from typing import Any

from app.services.agent_harness.tools.edit import _unified_diff
from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class WriteTool:
    spec = ToolSpec(
        name="write",
        description=(
            "Create or completely replace a text file in the workspace. Parent "
            "directories are created when allowed. Returns a unified diff."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "content": {"type": "string"},
            },
            "required": ["path", "content"],
            "additionalProperties": False,
        },
        replay_policy="verify",
        display_name="Write",
        category="write",
        summary="Write file",
        input_summary_fields=("path",),
        mutates_workspace=True,
        path_argument="path",
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        content = arguments.get("content")
        if not isinstance(content, str):
            raise ValueError("content must be text")
        path, original, changed = await context.backend.write_text(
            arguments.get("path"), content
        )
        return {
            "path": path,
            "bytes_written": len(content.encode("utf-8")),
            "changed": changed,
            "diff": (
                _unified_diff(path.rsplit("/", 1)[-1], original, content)
                if changed
                else ""
            ),
        }
