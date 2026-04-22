"""File operation tools for the agent.

Provides file_read, file_write, and file_edit tools for safe workspace
file manipulation with security constraints.
"""

from __future__ import annotations

import asyncio
import difflib
import os
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.agent.tools import register_tool

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Security constraints
MAX_READ_SIZE_BYTES = 50 * 1024  # 50KB
MAX_WRITE_SIZE_BYTES = 1024 * 1024  # 1MB
DEFAULT_READ_LIMIT = 500

# Blocked path patterns for write operations
BLOCKED_PATTERNS = [
    ".git/",
    ".git\\",
    "*.pyc",
    "__pycache__/",
    "__pycache__\\",
    ".env",
    ".env.*",
    "*.pem",
    "*.key",
]


def _is_path_blocked(path: str) -> bool:
    """Check if a path matches any blocked pattern."""
    import fnmatch

    path_lower = path.lower()
    for pattern in BLOCKED_PATTERNS:
        if fnmatch.fnmatch(path_lower, pattern):
            return True
        if fnmatch.fnmatch(path_lower, f"*/{pattern}"):
            return True
        if fnmatch.fnmatch(path_lower, f"*\\{pattern}"):
            return True
        # Check if path contains .git/ anywhere
        if ".git/" in path_lower or ".git\\" in path_lower:
            return True
    return False


def _is_binary_file(path: Path, sample_size: int = 8192) -> bool:
    """Check if a file appears to be binary by sampling content."""
    try:
        with open(path, "rb") as f:
            sample = f.read(sample_size)
        # Check for null bytes (common in binary files)
        if b"\x00" in sample:
            return True
        # Try to decode as text
        try:
            sample.decode("utf-8")
            return False
        except UnicodeDecodeError:
            return True
    except Exception:
        return True


def _format_with_line_numbers(content: str, start_line: int = 1) -> str:
    """Format content with line numbers."""
    lines = content.splitlines(keepends=True)
    formatted = []
    for i, line in enumerate(lines, start=start_line):
        # Right-align line numbers up to 6 digits
        formatted.append(f"{i:6}| {line}")
    return "".join(formatted)


@register_tool
class FileReadTool(BaseTool):
    """Tool to read text files from the workspace."""

    name = "file_read"
    description = (
        "Read any text file in the workspace with optional line offset and limit."
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
            "path": {
                "type": "string",
                "description": "Relative path to the file within the workspace",
                "required": True,
            },
            "offset": {
                "type": "integer",
                "description": "Starting line number (0-indexed)",
                "default": 0,
            },
            "limit": {
                "type": "integer",
                "description": "Maximum number of lines to return",
                "default": DEFAULT_READ_LIMIT,
            },
            "encoding": {
                "type": "string",
                "description": "File encoding",
                "default": "utf-8",
            },
        }

    async def execute(
        self,
        *,
        path: str,
        offset: int = 0,
        limit: int = DEFAULT_READ_LIMIT,
        encoding: str = "utf-8",
    ) -> ToolResult:
        """Read a file from the workspace.

        Args:
            path: Relative path to the file
            offset: Starting line number (0-indexed)
            limit: Maximum lines to return
            encoding: File encoding (default: utf-8)

        Returns:
            ToolResult with file content and metadata
        """
        try:
            root = await self._get_workspace_root()
            target = self._safe_path(root, path)

            if not target.exists():
                return ToolResult(success=False, error=f"File not found: {path}")

            if not target.is_file():
                return ToolResult(success=False, error=f"Path is not a file: {path}")

            # Check file size
            file_size = target.stat().st_size
            if file_size > MAX_READ_SIZE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"File too large: {file_size} bytes (max: {MAX_READ_SIZE_BYTES} bytes)",
                )

            # Check if binary
            if await asyncio.to_thread(_is_binary_file, target):
                return ToolResult(
                    success=False,
                    error="Cannot read binary file. Use a specialized tool for binary formats.",
                )

            # Read the file
            def _read_file_lines() -> tuple[list[str], int]:
                result: list[str] = []
                count = 0
                with target.open("r", encoding=encoding, errors="replace") as f:
                    for i, line in enumerate(f):
                        if i >= offset and len(result) < limit:
                            result.append(line)
                        count += 1
                return result, count

            try:
                content_lines, total_lines = await asyncio.to_thread(_read_file_lines)
            except UnicodeDecodeError as e:
                return ToolResult(success=False, error=f"Encoding error: {e}")

            content = "".join(content_lines)
            truncated = offset + limit < total_lines

            # Format with line numbers
            formatted_content = _format_with_line_numbers(
                content, start_line=offset + 1
            )

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "content": formatted_content,
                    "total_lines": total_lines,
                    "offset": offset,
                    "limit": limit,
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


@register_tool
class GlobTool(BaseTool):
    """Tool to find files by glob pattern within the workspace."""

    name = "glob"
    description = (
        "Find files matching a glob pattern in the workspace. "
        "Returns paths sorted by modification time (newest first). "
        "Use '**/*.py' for recursive, '*.py' for top-level only."
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
                "description": (
                    "Glob pattern to match files. "
                    "Use '**/*.py' for recursive search, '*.py' for top-level."
                ),
                "required": True,
            },
        }

    async def execute(
        self,
        *,
        pattern: str,
    ) -> ToolResult:
        """Find files matching a glob pattern.

        Args:
            pattern: Glob pattern (e.g., '**/*.py', 'src/*.nf')

        Returns:
            ToolResult with matching file paths sorted by mtime (newest first)
        """
        try:
            if not pattern.strip():
                return ToolResult(success=False, error="pattern cannot be empty")

            # Block path traversal in patterns
            if ".." in pattern:
                return ToolResult(
                    success=False, error="pattern escapes workspace (contains '..')"
                )

            root = await self._get_workspace_root()

            # Run glob in a thread to avoid blocking the event loop
            def _do_glob() -> list[tuple[str, float]]:
                results: list[tuple[str, float]] = []
                for match in root.glob(pattern):
                    if not match.is_file():
                        continue
                    # Ensure match is within workspace
                    resolved = match.resolve()
                    if not resolved.is_relative_to(root.resolve()):
                        continue
                    rel = str(match.relative_to(root))
                    mtime = match.stat().st_mtime
                    results.append((rel, mtime))
                return results

            raw = await asyncio.to_thread(_do_glob)

            # Sort by mtime descending (newest first)
            raw.sort(key=lambda x: x[1], reverse=True)
            paths = [p for p, _ in raw]

            return ToolResult(
                success=True,
                data={
                    "pattern": pattern,
                    "total_matches": len(paths),
                    "matches": paths,
                },
            )

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")


@register_tool
class FileWriteTool(BaseTool):
    """Tool to create or overwrite files in the workspace."""

    name = "file_write"
    description = "Create or overwrite a text file in the workspace."
    risk_level = RiskLevel.ACT_LOW

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
            "path": {
                "type": "string",
                "description": "Target file path relative to workspace",
                "required": True,
            },
            "content": {
                "type": "string",
                "description": "Content to write to the file",
                "required": True,
            },
            "create_dirs": {
                "type": "boolean",
                "description": "Create parent directories if they don't exist",
                "default": True,
            },
            "overwrite": {
                "type": "boolean",
                "description": "Overwrite existing file if it exists",
                "default": False,
            },
        }

    async def execute(
        self,
        *,
        path: str,
        content: str,
        create_dirs: bool = True,
        overwrite: bool = False,
    ) -> ToolResult:
        """Write content to a file.

        Args:
            path: Target file path
            content: Content to write
            create_dirs: Create parent directories if needed
            overwrite: Allow overwriting existing files

        Returns:
            ToolResult with file metadata
        """
        try:
            # Check blocked patterns
            if _is_path_blocked(path):
                return ToolResult(
                    success=False,
                    error=f"Writing to path '{path}' is not allowed (blocked pattern)",
                )

            # Check content size
            content_bytes = content.encode("utf-8")
            if len(content_bytes) > MAX_WRITE_SIZE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"Content too large: {len(content_bytes)} bytes (max: {MAX_WRITE_SIZE_BYTES} bytes)",
                )

            root = await self._get_workspace_root()
            target = self._safe_path(root, path)

            # Check if file exists
            file_existed = target.exists()
            if file_existed and not overwrite:
                return ToolResult(
                    success=False,
                    error=f"File already exists: {path}. Set overwrite=true to replace it.",
                )

            # Create directories if needed
            if create_dirs:
                target.parent.mkdir(parents=True, exist_ok=True)
            elif not target.parent.exists():
                return ToolResult(
                    success=False,
                    error=f"Parent directory does not exist: {target.parent.relative_to(root)}",
                )

            # Write the file
            target.write_text(content, encoding="utf-8")

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "size_bytes": len(content_bytes),
                    "created": not file_existed,
                    "overwritten": file_existed,
                },
            )

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")


@register_tool
class FileEditTool(BaseTool):
    """Tool for precise text replacement in files."""

    name = "file_edit"
    description = (
        "Edit a file by replacing exact text content. Uses atomic writes for safety."
    )
    risk_level = RiskLevel.ACT_LOW

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
            "path": {
                "type": "string",
                "description": "File path relative to workspace",
                "required": True,
            },
            "old_content": {
                "type": "string",
                "description": "Exact text to find and replace",
                "required": True,
            },
            "new_content": {
                "type": "string",
                "description": "Replacement text",
                "required": True,
            },
            "expected_count": {
                "type": "integer",
                "description": "Expected number of occurrences to replace",
                "default": 1,
            },
        }

    async def execute(
        self,
        *,
        path: str,
        old_content: str,
        new_content: str,
        expected_count: int = 1,
    ) -> ToolResult:
        """Edit a file by replacing text.

        Args:
            path: Target file path
            old_content: Text to find
            new_content: Replacement text
            expected_count: Expected occurrences (for validation)

        Returns:
            ToolResult with replacement info and diff
        """
        try:
            # Check blocked patterns
            if _is_path_blocked(path):
                return ToolResult(
                    success=False,
                    error=f"Editing path '{path}' is not allowed (blocked pattern)",
                )

            root = await self._get_workspace_root()
            target = self._safe_path(root, path)

            if not target.exists():
                return ToolResult(success=False, error=f"File not found: {path}")

            if not target.is_file():
                return ToolResult(success=False, error=f"Path is not a file: {path}")

            # Read current content
            try:
                original_content = target.read_text(encoding="utf-8")
            except UnicodeDecodeError as e:
                return ToolResult(
                    success=False, error=f"Cannot read file (encoding error): {e}"
                )

            # Count occurrences
            occurrence_count = original_content.count(old_content)
            if occurrence_count == 0:
                return ToolResult(
                    success=False,
                    error="Text to replace not found in file",
                )

            if expected_count > 0 and occurrence_count != expected_count:
                return ToolResult(
                    success=False,
                    error=f"Expected {expected_count} occurrence(s), found {occurrence_count}",
                )

            # Perform replacement
            new_file_content = original_content.replace(old_content, new_content)

            # Check size limit
            if len(new_file_content.encode("utf-8")) > MAX_WRITE_SIZE_BYTES:
                return ToolResult(
                    success=False,
                    error=f"Resulting file too large (max: {MAX_WRITE_SIZE_BYTES} bytes)",
                )

            # Generate diff
            original_lines = original_content.splitlines(keepends=True)
            new_lines = new_file_content.splitlines(keepends=True)
            diff = list(
                difflib.unified_diff(
                    original_lines,
                    new_lines,
                    fromfile=f"a/{path}",
                    tofile=f"b/{path}",
                    lineterm="",
                )
            )
            diff_str = "".join(diff)

            # Atomic write: write to temp file, then rename
            dir_fd = os.open(str(target.parent), os.O_RDONLY)
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w",
                    encoding="utf-8",
                    dir=target.parent,
                    delete=False,
                ) as tmp:
                    tmp.write(new_file_content)
                    tmp_path = Path(tmp.name)

                # Atomic rename
                tmp_path.rename(target)
            finally:
                os.close(dir_fd)

            return ToolResult(
                success=True,
                data={
                    "path": path,
                    "replacements": occurrence_count,
                    "diff": diff_str,
                },
            )

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")
