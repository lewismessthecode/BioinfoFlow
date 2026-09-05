from __future__ import annotations

import mimetypes
from pathlib import Path
from typing import Any

from app.services.agent_harness.tools.specs import ToolExecutionContext, ToolSpec


class PublishArtifactTool:
    """Make one explicit, managed Artifact copy from a workspace result."""

    spec = ToolSpec(
        name="publish_artifact",
        description=(
            "Publish one existing workspace file as a durable user-facing artifact. "
            "Use this only for a result the user should be able to download after "
            "the Agent run ends."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "path": {"type": "string", "minLength": 1},
                "title": {"type": "string", "minLength": 1, "maxLength": 200},
                "summary": {"type": "string", "maxLength": 4000},
            },
            "required": ["path"],
            "additionalProperties": False,
        },
        replay_policy="safe",
        display_name="Publish artifact",
        category="write",
        summary="Publish artifact",
        input_summary_fields=("path", "title"),
        mutates_workspace=False,
        path_argument="path",
        serial=True,
    )

    async def run(
        self, arguments: dict[str, Any], context: ToolExecutionContext
    ) -> dict[str, Any]:
        writer = getattr(context.backend, "artifact_writer", None)
        if not callable(writer):
            raise ValueError("Artifact publishing is unavailable for this Agent run")
        path, content = await context.backend.read_publishable_file(
            arguments.get("path")
        )
        filename = Path(path).name
        title = str(arguments.get("title") or filename).strip()
        if not title:
            raise ValueError("artifact title must be non-empty text")
        summary = arguments.get("summary")
        if summary is not None and not isinstance(summary, str):
            raise ValueError("artifact summary must be text")
        mime_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"
        artifact = await writer(
            {
                "type": "published_file",
                "declaration_id": f"tool:{context.call_id}",
                "filename": filename,
                "title": title,
                "summary": summary.strip() if isinstance(summary, str) else None,
                "mime_type": mime_type,
                "content": content,
            }
        )
        return {"path": path, "artifact": artifact}
