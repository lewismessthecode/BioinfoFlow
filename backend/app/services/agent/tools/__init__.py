"""Agent tools registry and exports."""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.services.agent.tools.base import BaseTool, RiskLevel, ToolResult

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.ext.asyncio import AsyncSession


# Tool registry - maps tool names to their classes
_TOOL_REGISTRY: dict[str, type[BaseTool]] = {}


def register_tool(tool_class: type[BaseTool]) -> type[BaseTool]:
    """Decorator to register a tool class in the registry.

    Usage:
        @register_tool
        class MyTool(BaseTool):
            name = "my_tool"
            ...
    """
    _TOOL_REGISTRY[tool_class.name] = tool_class
    return tool_class


def get_tool_class(name: str) -> type[BaseTool] | None:
    """Get a tool class by name from the registry."""
    return _TOOL_REGISTRY.get(name)


def list_tool_names() -> list[str]:
    """List all registered tool names."""
    return list(_TOOL_REGISTRY.keys())


def create_tool(
    name: str,
    session: "AsyncSession",
    *,
    project_id: str,
    workspace_root: "Path | None" = None,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> BaseTool | None:
    """Create a tool instance by name.

    Args:
        name: Tool name from registry
        session: Database session
        project_id: Project ID
        workspace_root: Optional pre-resolved workspace root
        user_id: Authenticated user ID (for platform_* auth scoping)
        workspace_id: Workspace ID (for platform_* auth scoping)

    Returns:
        Tool instance or None if not found
    """
    tool_class = get_tool_class(name)
    if tool_class is None:
        return None
    return tool_class(
        session,
        project_id=project_id,
        workspace_root=workspace_root,
        user_id=user_id,
        workspace_id=workspace_id,
    )


def get_all_tools(
    session: "AsyncSession",
    *,
    project_id: str,
    workspace_root: "Path | None" = None,
    allow_workspace_tools: bool = True,
    user_id: str | None = None,
    workspace_id: str | None = None,
) -> list[BaseTool]:
    """Create instances of all registered tools.

    Args:
        session: Database session
        project_id: Project ID
        workspace_root: Optional pre-resolved workspace root
        allow_workspace_tools: When False, filesystem/shell/code tools are
            omitted (e.g. sandboxed conversations that shouldn't hit disk).
        user_id: Authenticated user ID, forwarded to platform_* tools.
        workspace_id: Workspace ID, forwarded to platform_* tools.

    Returns:
        List of tool instances
    """
    workspace_bound_tools = {
        "file_read",
        "file_write",
        "file_edit",
        "glob",
        "grep",
        "code_search",
        "shell",
        "execute_code",
    }
    return [
        tool_class(
            session,
            project_id=project_id,
            workspace_root=workspace_root,
            user_id=user_id,
            workspace_id=workspace_id,
        )
        for tool_class in _TOOL_REGISTRY.values()
        if allow_workspace_tools or tool_class.name not in workspace_bound_tools
    ]


# Import tool modules to trigger @register_tool decorators
from app.services.agent.tools.file_tools import (  # noqa: F401, E402
    FileReadTool,
    FileWriteTool,
    FileEditTool,
    GlobTool,
)
from app.services.agent.tools.search_tools import GrepTool, CodeSearchTool  # noqa: F401, E402
from app.services.agent.tools.code_tools import ExecuteCodeTool  # noqa: F401, E402
from app.services.agent.tools.shell_tool import ShellTool  # noqa: F401, E402
from app.services.agent.tools.web_tools import (  # noqa: F401, E402
    ChemblSearchTool,
    PubMedSearchTool,
    WebFetchTool,
    WebSearchTool,
)
from app.services.agent.tools import platform_tools  # noqa: F401, E402
from app.services.agent.tools.run_tools import (  # noqa: F401, E402
    RunSubmitTool,
    RunGetTool,
    RunGetDagTool,
    RunGetResultsTool,
)


def get_tool_risk_level(name: str) -> str:
    """Get the risk level for a tool by name.

    Args:
        name: Tool name

    Returns:
        Risk level string (read, act_low, act_high)
    """
    tool_class = get_tool_class(name)
    if tool_class is None:
        return RiskLevel.READ
    return getattr(tool_class, "risk_level", RiskLevel.READ)


__all__ = [
    # Tool infrastructure
    "BaseTool",
    "RiskLevel",
    "ToolResult",
    "register_tool",
    "get_tool_class",
    "get_tool_risk_level",
    "list_tool_names",
    "create_tool",
    "get_all_tools",
    # Tool classes
    "FileReadTool",
    "FileWriteTool",
    "FileEditTool",
    "GlobTool",
    "GrepTool",
    "CodeSearchTool",
    "ExecuteCodeTool",
    "ShellTool",
    "WebSearchTool",
    "WebFetchTool",
    "PubMedSearchTool",
    "ChemblSearchTool",
    "RunSubmitTool",
    "RunGetTool",
    "RunGetDagTool",
    "RunGetResultsTool",
]
