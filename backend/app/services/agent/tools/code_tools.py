"""Code execution tools for the agent.

Provides execute_code tool for running Python code with optional sandboxing.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.config import settings
from app.services.agent.tools import register_tool
from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult
from app.services.agent.tools.sandbox import CodeSandbox

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


# Limits
MAX_CODE_SIZE = 50 * 1024  # 50KB
MAX_TIMEOUT = 300  # 5 minutes
DEFAULT_TIMEOUT = 30


@register_tool
class ExecuteCodeTool(BaseTool):
    """Tool to execute Python code with optional sandboxing."""

    name = "execute_code"
    description = (
        "Execute Python code in the workspace. "
        "Code is written to a temp file and executed with a timeout. "
        "Returns stdout, stderr, exit code, and any generated artifacts."
    )
    risk_level = RiskLevel.ACT_HIGH  # Requires approval in SAFE_AUTO mode

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
            "code": {
                "type": "string",
                "description": "Python code to execute",
                "required": True,
            },
            "timeout": {
                "type": "integer",
                "description": f"Maximum execution time in seconds (default: {DEFAULT_TIMEOUT}, max: {MAX_TIMEOUT})",
                "default": DEFAULT_TIMEOUT,
            },
            "working_dir": {
                "type": "string",
                "description": "Working directory relative to workspace (default: '.')",
                "default": ".",
            },
        }

    async def execute(
        self,
        *,
        code: str,
        timeout: int = DEFAULT_TIMEOUT,
        working_dir: str = ".",
    ) -> ToolResult:
        """Execute Python code.

        Args:
            code: Python code to execute
            timeout: Maximum execution time in seconds
            working_dir: Working directory relative to workspace

        Returns:
            ToolResult with execution output and artifacts
        """
        try:
            # Validate inputs
            if not code.strip():
                return ToolResult(success=False, error="code cannot be empty")

            code_bytes = code.encode("utf-8")
            if len(code_bytes) > MAX_CODE_SIZE:
                return ToolResult(
                    success=False,
                    error=f"code too large: {len(code_bytes)} bytes (max: {MAX_CODE_SIZE})",
                )

            # Clamp timeout
            timeout = max(1, min(timeout, MAX_TIMEOUT))

            # Resolve workspace and working directory
            root = await self._get_workspace_root()
            cwd = self._safe_path(root, working_dir)

            if not cwd.exists():
                return ToolResult(
                    success=False,
                    error=f"working directory not found: {working_dir}",
                )

            if not cwd.is_dir():
                return ToolResult(
                    success=False,
                    error=f"working_dir is not a directory: {working_dir}",
                )

            # Snapshot existing files for artifact detection
            files_before = self._snapshot_files(cwd)

            # Write code to temp file in workspace
            script_name = f"_agent_exec_{uuid.uuid4().hex[:8]}.py"
            script_path = cwd / script_name

            try:
                script_path.write_text(code, encoding="utf-8")

                # Execute with sandbox
                sandbox = CodeSandbox(
                    workspace_root=root,
                    enabled=settings.agent_sandbox_enabled,
                )

                result = await sandbox.execute(
                    script_path=script_path,
                    timeout=timeout,
                    working_dir=cwd,
                )

                # Detect new files (artifacts)
                files_after = self._snapshot_files(cwd)
                artifacts = self._detect_artifacts(
                    files_before, files_after, script_name
                )

                return ToolResult(
                    success=result.exit_code == 0 and not result.timed_out,
                    data={
                        "stdout": result.stdout,
                        "stderr": result.stderr,
                        "exit_code": result.exit_code,
                        "timed_out": result.timed_out,
                        "artifacts": artifacts,
                    },
                    error=result.stderr if result.exit_code != 0 else None,
                )

            finally:
                # Clean up temp script
                script_path.unlink(missing_ok=True)

        except PermissionError as e:
            return ToolResult(success=False, error=str(e))
        except FileNotFoundError as e:
            return ToolResult(success=False, error=str(e))
        except Exception as e:
            return ToolResult(success=False, error=f"Unexpected error: {e}")

    def _snapshot_files(self, directory: Path) -> set[str]:
        """Get set of files in directory (non-recursive for now)."""
        try:
            return {f.name for f in directory.iterdir() if f.is_file()}
        except Exception:
            return set()

    def _detect_artifacts(
        self,
        before: set[str],
        after: set[str],
        exclude_script: str,
    ) -> list[dict[str, Any]]:
        """Detect newly created files (artifacts)."""
        new_files = after - before
        new_files.discard(exclude_script)  # Exclude our temp script

        artifacts = []
        for name in sorted(new_files):
            artifacts.append(
                {
                    "name": name,
                    "type": self._guess_artifact_type(name),
                }
            )

        return artifacts

    def _guess_artifact_type(self, filename: str) -> str:
        """Guess artifact type from filename."""
        suffix = Path(filename).suffix.lower()

        type_map = {
            ".png": "image",
            ".jpg": "image",
            ".jpeg": "image",
            ".gif": "image",
            ".svg": "image",
            ".pdf": "document",
            ".csv": "data",
            ".tsv": "data",
            ".json": "data",
            ".html": "document",
            ".txt": "text",
            ".log": "log",
            ".npy": "data",
            ".npz": "data",
            ".pkl": "data",
            ".pickle": "data",
        }

        return type_map.get(suffix, "file")
