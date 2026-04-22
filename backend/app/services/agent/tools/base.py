"""Base classes for agent tools."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from app.path_layout import project_home
from app.repositories.project_repo import ProjectRepository

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


class RiskLevel:
    """Risk level constants for tools.

    Tools are categorized by their potential impact:
    - READ: Read-only operations (file_read, code_search, etc.)
    - ACT_LOW: Low-risk modifications (file_write, file_edit)
    - ACT_HIGH: High-risk operations requiring approval (run_create, execute_code)
    """

    READ = "read"
    ACT_LOW = "act_low"
    ACT_HIGH = "act_high"


@dataclass
class ToolResult:
    """Standard result container for tool execution."""

    success: bool
    data: dict[str, Any] | None = None
    error: str | None = None
    truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for serialization."""
        result: dict[str, Any] = {"success": self.success}
        if self.data is not None:
            result["data"] = self.data
        if self.error is not None:
            result["error"] = self.error
        if self.truncated:
            result["truncated"] = True
        return result


class BaseTool(ABC):
    """Abstract base class for all agent tools."""

    name: str
    description: str
    risk_level: str = RiskLevel.READ  # Default to read-only

    def __init__(
        self,
        session: AsyncSession,
        *,
        project_id: str,
        workspace_root: Path | None = None,
        user_id: str | None = None,
        workspace_id: str | None = None,
    ) -> None:
        """Initialize tool with session and project context.

        Args:
            session: Database session for repository access
            project_id: Project ID for workspace resolution
            workspace_root: Optional pre-resolved workspace root path
            user_id: Authenticated user ID for service-layer auth scoping
            workspace_id: Workspace ID for service-layer auth scoping
        """
        self.session = session
        self.project_id = project_id
        self._workspace_root = workspace_root
        self.user_id = user_id
        self.workspace_id = workspace_id
        self._project_repo = ProjectRepository(session)

    @abstractmethod
    async def execute(self, **kwargs: Any) -> ToolResult:
        """Execute the tool with given parameters.

        Returns:
            ToolResult with success status and data or error
        """
        pass

    @abstractmethod
    def get_schema(self) -> dict[str, Any]:
        """Get JSON schema for tool parameters.

        Returns:
            Dictionary describing tool parameters in JSON schema format
        """
        pass

    def effective_risk_level(self, tool_input: dict[str, Any]) -> str:  # noqa: ARG002
        """Resolve the risk level for a single invocation.

        The class attribute ``risk_level`` is a coarse default. Some tools
        (notably shell) can safely self-lower when the concrete input is
        obviously read-only — ``ls``, ``git status``, ``bif workflow list``,
        etc. — avoiding a per-call approval prompt for commands that have
        no side effects. Overrides must only *lower* the declared level,
        never raise it.
        """
        return self.risk_level

    def get_definition(self) -> dict[str, Any]:
        """Get tool definition for LLM binding.

        Returns:
            Dictionary with name, description, and args schema
        """
        return {
            "name": self.name,
            "description": self.description,
            "args": self.get_schema(),
        }

    async def _get_workspace_root(self) -> Path:
        """Get workspace root, resolving from project if not provided."""
        if self._workspace_root:
            return self._workspace_root

        project = await self._project_repo.get(self.project_id)
        if not project:
            raise FileNotFoundError("project not found")

        root = project_home(project)
        return root

    def _safe_path(self, root: Path, relative_path: str) -> Path:
        """Validate and resolve a path within workspace bounds.

        Args:
            root: Workspace root directory
            relative_path: Path relative to workspace root

        Returns:
            Resolved absolute path

        Raises:
            PermissionError: If path escapes workspace bounds
        """
        target = (root / relative_path).resolve()
        if not target.is_relative_to(root):
            raise PermissionError("path escapes workspace")
        return target
