from __future__ import annotations

from typing import Any

from app.config import settings
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError

_MAX_RESULTS_CAP = 1000


class GlobTool:
    """List files matching a glob pattern within the allowed roots.

    A read-only path tool (concurrency-safe) so a ``worker``/``plan`` agent can
    discover files without ``bash``. The base directory is confined to
    :class:`FilesystemPolicy` allowed roots; results are sorted file paths.
    """

    spec = AgentToolSpec(
        name="glob",
        description=(
            "List files matching a glob pattern (e.g. '**/*.py') within the "
            "workspace. Returns sorted file paths. Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "path": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS_CAP},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "paths": {"type": "array"},
                "count": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
            "required": ["paths", "count", "truncated"],
        },
        risk_level="read",
        read_scope=["workspace"],
        audit="List files matching a glob within the allowed workspace.",
        timeout_seconds=30,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        pattern = input.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise BadRequestError("pattern must be a non-empty string")
        if pattern.startswith("/"):
            raise BadRequestError("pattern must be relative to the search path")
        base = FilesystemPolicy().require_allowed_dir(input.get("path") or str(settings.repo_root))
        max_results = min(int(input.get("max_results") or 200), _MAX_RESULTS_CAP)

        paths: list[str] = []
        for candidate in sorted(base.glob(pattern)):
            if candidate.is_file():
                paths.append(str(candidate))
            if len(paths) > max_results:
                break
        truncated = len(paths) > max_results
        return {
            "paths": paths[:max_results],
            "count": min(len(paths), max_results),
            "truncated": truncated,
        }
