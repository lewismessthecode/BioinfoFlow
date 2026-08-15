from __future__ import annotations

import difflib
from typing import Any

from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class EditTool:
    spec = ToolSpec(
        name="edit",
        description=(
            "Replace exact text in one workspace file. The old text must match "
            "exactly once unless replace_all is true. Returns a unified diff."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "old_text": {"type": "string"},
                "new_text": {"type": "string"},
                "replace_all": {"type": "boolean"},
            },
            "required": ["path", "old_text", "new_text"],
            "additionalProperties": False,
        },
        replay_policy="verify",
        display_name="Edit",
        category="edit",
        summary="Edit file",
        input_summary_fields=("path",),
        mutates_workspace=True,
        path_argument="path",
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")
        if not isinstance(old_text, str) or not isinstance(new_text, str):
            raise ValueError("old_text and new_text must be text")
        if old_text == new_text:
            raise ValueError("old_text and new_text must differ")
        replace_all = arguments.get("replace_all") is True
        path, original, updated, replacements = await context.backend.edit_text(
            arguments.get("path"),
            old_text=old_text,
            new_text=new_text,
            replace_all=replace_all,
        )
        return {
            "path": path,
            "replacements": replacements,
            "diff": _unified_diff(path.rsplit("/", 1)[-1], original, updated),
        }


def _unified_diff(name: str, before: str, after: str) -> str:
    return "".join(
        difflib.unified_diff(
            before.splitlines(keepends=True),
            after.splitlines(keepends=True),
            fromfile=f"a/{name}",
            tofile=f"b/{name}",
        )
    )
