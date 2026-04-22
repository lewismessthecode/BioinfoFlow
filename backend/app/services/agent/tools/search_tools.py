"""Code search tools for the agent.

Provides grep tool for searching code using ripgrep with structured output.
"""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent.tools import register_tool
from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Limits
MAX_RESULTS = 100
MAX_CONTEXT_LINES = 10


class RipgrepNotFoundError(Exception):
    """Raised when ripgrep is not available."""

    pass


def _check_ripgrep_available() -> str:
    """Check if ripgrep is available and return its path.

    Returns:
        Path to ripgrep executable

    Raises:
        RipgrepNotFoundError: If ripgrep is not installed
    """
    rg_path = shutil.which("rg")
    if not rg_path:
        raise RipgrepNotFoundError(
            "ripgrep not found. Install with:\n"
            "  macOS: brew install ripgrep\n"
            "  Linux: apt install ripgrep\n"
            "  Windows: choco install ripgrep"
        )
    return rg_path


def _parse_ripgrep_json(line: str) -> dict[str, Any] | None:
    """Parse a single JSON line from ripgrep output.

    Args:
        line: JSON line from ripgrep --json output

    Returns:
        Parsed match data or None if not a match line
    """
    try:
        data = json.loads(line)
        if data.get("type") == "match":
            return data
        return None
    except json.JSONDecodeError:
        return None


@register_tool
class GrepTool(BaseTool):
    """Tool to search code using ripgrep."""

    name = "grep"
    description = (
        "Search code files using regex patterns with ripgrep. "
        "Returns matching lines with context and file locations."
    )
    risk_level = RiskLevel.READ

    def __init__(
        self,
        session: "AsyncSession",
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        super().__init__(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )

    def get_schema(self) -> dict[str, Any]:
        return {
            "pattern": {
                "type": "string",
                "description": "Regex pattern to search for",
                "required": True,
            },
            "path": {
                "type": "string",
                "description": "Search root relative to workspace (default: '.')",
                "default": ".",
            },
            "glob": {
                "type": "string",
                "description": "File glob filter (e.g., '*.py', '*.nf')",
                "default": None,
            },
            "file_types": {
                "type": "array",
                "items": {"type": "string"},
                "description": "File glob patterns to include (e.g., ['*.py', '*.nf'])",
                "default": [],
            },
            "case_insensitive": {
                "type": "boolean",
                "description": "Enable case-insensitive search",
                "default": False,
            },
            "context": {
                "type": "integer",
                "description": f"Lines of context before and after match (max: {MAX_CONTEXT_LINES})",
                "default": 2,
            },
            "max_results": {
                "type": "integer",
                "description": f"Maximum number of matches to return (max: {MAX_RESULTS})",
                "default": 50,
            },
        }

    async def execute(
        self,
        *,
        pattern: str,
        path: str = ".",
        glob: str | None = None,
        file_types: list[str] | None = None,
        case_insensitive: bool = False,
        context: int = 2,
        max_results: int = 50,
    ) -> ToolResult:
        """Search code using ripgrep.

        Args:
            pattern: Regex pattern to search
            path: Search root relative to workspace
            glob: Single file glob filter (e.g., '*.py')
            file_types: File patterns to include (list form)
            case_insensitive: Case-insensitive matching
            context: Context lines around matches
            max_results: Maximum matches to return

        Returns:
            ToolResult with search results
        """
        try:
            # Validate inputs
            if not pattern.strip():
                return ToolResult(success=False, error="pattern cannot be empty")

            max_results = min(max_results, MAX_RESULTS)
            context = min(context, MAX_CONTEXT_LINES)
            file_types = file_types or []

            # Check ripgrep availability
            try:
                rg_path = _check_ripgrep_available()
            except RipgrepNotFoundError as e:
                return ToolResult(success=False, error=str(e))

            # Resolve search path
            root = await self._get_workspace_root()
            search_path = self._safe_path(root, path)

            if not search_path.exists():
                return ToolResult(success=False, error=f"path not found: {path}")

            # Build ripgrep command
            cmd = [
                rg_path,
                "--json",  # Structured JSON output
                "--max-count",
                str(max_results * 2),  # Get extra for grouping
            ]

            # Case sensitivity
            if case_insensitive:
                cmd.append("--ignore-case")

            # Context lines
            if context > 0:
                cmd.extend(["--context", str(context)])

            # Single glob filter (new parameter)
            if glob:
                cmd.extend(["--glob", glob])

            # File type filters (backward compat)
            for ft in file_types:
                cmd.extend(["--glob", ft])

            # Add pattern and path
            cmd.append(pattern)
            cmd.append(str(search_path))

            # Execute ripgrep
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=str(root),
            )

            stdout, stderr = await proc.communicate()

            # Handle errors
            if proc.returncode not in (0, 1):  # 1 = no matches, which is OK
                error_msg = stderr.decode("utf-8", errors="replace").strip()
                if error_msg:
                    return ToolResult(
                        success=False, error=f"ripgrep error: {error_msg}"
                    )
                return ToolResult(
                    success=False,
                    error=f"ripgrep failed with code {proc.returncode}",
                )

            # Parse results
            output = stdout.decode("utf-8", errors="replace")
            matches: list[dict[str, Any]] = []
            truncated = False

            for line in output.splitlines():
                match_data = _parse_ripgrep_json(line)
                if match_data is None:
                    continue

                # Extract relevant fields
                data = match_data.get("data", {})
                path_data = data.get("path", {})
                lines_data = data.get("lines", {})

                # Get file path relative to workspace
                abs_path = path_data.get("text", "")
                try:
                    rel_path = str(Path(abs_path).relative_to(root))
                except ValueError:
                    rel_path = abs_path

                # Get line number and content
                line_number = data.get("line_number", 0)
                line_text = lines_data.get("text", "").rstrip("\n")

                # Get match offsets for highlighting info
                submatches = data.get("submatches", [])
                match_ranges = [
                    {"start": sm.get("start", 0), "end": sm.get("end", 0)}
                    for sm in submatches
                ]

                matches.append(
                    {
                        "path": rel_path,
                        "line_number": line_number,
                        "content": line_text,
                        "matches": match_ranges,
                    }
                )

                if len(matches) >= max_results:
                    truncated = True
                    break

            # Group matches by file for better readability
            files: dict[str, list[dict[str, Any]]] = {}
            for match in matches:
                file_path = match["path"]
                if file_path not in files:
                    files[file_path] = []
                files[file_path].append(
                    {
                        "line": match["line_number"],
                        "content": match["content"],
                        "matches": match["matches"],
                    }
                )

            return ToolResult(
                success=True,
                data={
                    "pattern": pattern,
                    "search_path": path,
                    "total_matches": len(matches),
                    "files_with_matches": len(files),
                    "results": files,
                    "truncated": truncated,
                },
                truncated=truncated,
            )

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")


# Backward compatibility alias
CodeSearchTool = GrepTool
