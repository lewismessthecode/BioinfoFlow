from __future__ import annotations

from pathlib import Path
from typing import Any

from app.config import settings
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


class WorkspaceSearchTool:
    spec = AgentToolSpec(
        name="search.workspace",
        description="Search text files within an allowed workspace path.",
        input_schema={
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "path": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 200},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {"matches": {"type": "array"}, "root": {"type": "string"}},
            "required": ["matches", "root"],
        },
        risk_level="read",
        read_scope=["workspace"],
        audit="Search text files inside the allowed workspace.",
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        root = _resolve_root(input.get("path"))
        query = str(input["query"])
        limit = int(input.get("limit") or 50)
        matches: list[dict[str, Any]] = []
        for path in root.rglob("*"):
            if not path.is_file() or path.name.startswith("."):
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for line_number, line in enumerate(text.splitlines(), start=1):
                if query in line:
                    matches.append(
                        {
                            "path": str(path),
                            "line": line_number,
                            "text": line.strip(),
                        }
                    )
                    if len(matches) >= limit:
                        return {"root": str(root), "matches": matches}
        return {"root": str(root), "matches": matches}


def _resolve_root(raw_path: str | None) -> Path:
    candidate = Path(raw_path or settings.repo_root)
    if not candidate.is_absolute():
        candidate = Path(settings.repo_root) / candidate
    return FilesystemPolicy().require_allowed_dir(str(candidate))
