from __future__ import annotations

import asyncio
import re
import shutil
from pathlib import Path
from typing import Any

from app.config import settings
from app.services.agent_core.sandbox import FilesystemPolicy
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.utils.exceptions import BadRequestError
from app.utils.exceptions import PermissionDeniedError

_MAX_RESULTS_CAP = 500
_SCAN_FILE_CAP = 5000


class GrepTool:
    """Search file contents for a regular expression within the allowed roots.

    A genuine read tool (not a bash wrapper) so a read-only ``worker``/``plan``
    agent can search even when ``bash`` is hidden. Prefers ripgrep when present
    and falls back to a bounded Python ``re`` walk. The search directory is
    confined to :class:`FilesystemPolicy` allowed roots.
    """

    spec = AgentToolSpec(
        name="grep",
        description=(
            "Search file contents for a regular expression within the workspace. "
            "Returns matching file paths, line numbers, and lines. Read-only."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "minLength": 1},
                "path": {"type": "string"},
                "glob": {"type": "string"},
                "case_insensitive": {"type": "boolean"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": _MAX_RESULTS_CAP},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        output_schema={
            "type": "object",
            "properties": {
                "matches": {"type": "array"},
                "count": {"type": "integer"},
                "truncated": {"type": "boolean"},
            },
            "required": ["matches", "count", "truncated"],
        },
        risk_level="read",
        read_scope=["workspace"],
        audit="Search file contents within the allowed workspace.",
        timeout_seconds=30,
    )

    async def run(self, input: dict[str, Any], context: AgentToolContext) -> dict[str, Any]:
        del context
        pattern = input.get("pattern")
        if not isinstance(pattern, str) or not pattern:
            raise BadRequestError("pattern must be a non-empty string")
        base = FilesystemPolicy().require_allowed_dir(input.get("path") or str(settings.repo_root))
        glob = input.get("glob")
        if glob is not None:
            if not isinstance(glob, str) or not glob:
                raise BadRequestError("glob must be a non-empty string")
            _require_relative_glob_pattern(glob)
        case_insensitive = bool(input.get("case_insensitive", False))
        max_results = int(input.get("max_results") or 100)
        max_results = min(max_results, _MAX_RESULTS_CAP)

        if shutil.which("rg"):
            matches = await self._ripgrep(pattern, base, glob, case_insensitive, max_results)
        else:
            matches = self._python_grep(pattern, base, glob, case_insensitive, max_results)
        truncated = len(matches) > max_results
        return {
            "matches": matches[:max_results],
            "count": min(len(matches), max_results),
            "truncated": truncated,
        }

    async def _ripgrep(
        self, pattern: str, base: Path, glob: str | None, case_insensitive: bool, max_results: int
    ) -> list[dict[str, Any]]:
        argv = ["rg", "--no-heading", "--line-number", "--color=never", "--max-count", str(max_results)]
        if case_insensitive:
            argv.append("-i")
        if glob:
            argv.extend(["--glob", glob])
        argv.extend(["-e", pattern, str(base)])
        process = await asyncio.create_subprocess_exec(
            *argv,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, _stderr = await process.communicate()
        # rg exits 1 when there are no matches — not an error here.
        matches: list[dict[str, Any]] = []
        for raw in stdout.decode("utf-8", errors="replace").splitlines():
            parsed = _parse_rg_line(raw)
            if parsed is not None:
                matches.append(parsed)
            if len(matches) >= max_results + 1:
                break
        return matches

    def _python_grep(
        self, pattern: str, base: Path, glob: str | None, case_insensitive: bool, max_results: int
    ) -> list[dict[str, Any]]:
        flags = re.IGNORECASE if case_insensitive else 0
        try:
            regex = re.compile(pattern, flags)
        except re.error as exc:
            raise BadRequestError(f"invalid regex: {exc}") from exc
        matches: list[dict[str, Any]] = []
        scanned = 0
        policy = FilesystemPolicy()
        for file_path in sorted(base.rglob(glob or "*")):
            if scanned >= _SCAN_FILE_CAP or len(matches) > max_results:
                break
            try:
                target = policy.require_allowed_path(
                    file_path,
                    must_exist=True,
                    allow_directory=False,
                )
            except PermissionDeniedError:
                continue
            if not target.is_file():
                continue
            scanned += 1
            try:
                with target.open("r", encoding="utf-8", errors="strict") as handle:
                    for line_number, line in enumerate(handle, start=1):
                        if regex.search(line):
                            matches.append(
                                {
                                    "path": str(target),
                                    "line_number": line_number,
                                    "line": line.rstrip("\n")[:500],
                                }
                            )
                            if len(matches) > max_results:
                                break
            except (UnicodeDecodeError, OSError):
                continue  # skip binary / unreadable files
        return matches


def _parse_rg_line(raw: str) -> dict[str, Any] | None:
    parts = raw.split(":", 2)
    if len(parts) < 3:
        return None
    path, line_number, line = parts
    if not line_number.isdigit():
        return None
    return {"path": path, "line_number": int(line_number), "line": line[:500]}


def _require_relative_glob_pattern(pattern: str) -> None:
    path = Path(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise BadRequestError("glob must be relative to the search path")
