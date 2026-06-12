from app.path_layout import state_root
from app.services.agent_core.plugins import register_plugin_tools
from app.services.agent_core.tools.bio import (
    BuildImageCardTool,
    BuildWorkflowCardTool,
    DiagnoseRunTool,
    InterpretResultsTool,
    RunPreflightTool,
)
from app.services.agent_core.tools.dispatcher import AgentToolDispatcher
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.files import (
    EditFileTool,
    ListFilesTool,
    ReadFileTool,
    WriteFileTool,
)
from app.services.agent_core.tools.memory import ListMemoriesTool, ProposeMemoryTool
from app.services.agent_core.tools.platform import (
    GetRunLogsTool,
    ListImagesTool,
    ListProjectsTool,
    ListRunsTool,
    ListWorkflowsTool,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.search import WorkspaceSearchTool
from app.services.agent_core.tools.skills import (
    ListPluginsTool,
    ListSkillsTool,
    LoadSkillTool,
)
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.subagents import SubagentAnalyzeTool
from app.services.agent_core.tools.toolsets import ToolsetExposure
from app.services.agent_core.tools.web import FetchWebPageTool, SearchWebTool


def build_default_tool_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(BuildImageCardTool())
    registry.register(BuildWorkflowCardTool())
    registry.register(DiagnoseRunTool())
    registry.register(ExecuteShellTool())
    registry.register(EditFileTool())
    registry.register(FetchWebPageTool())
    registry.register(InterpretResultsTool())
    registry.register(ListFilesTool())
    registry.register(ListMemoriesTool())
    registry.register(ListPluginsTool())
    registry.register(ListImagesTool())
    registry.register(ListProjectsTool())
    registry.register(ListRunsTool())
    registry.register(ListSkillsTool())
    registry.register(GetRunLogsTool())
    registry.register(ListWorkflowsTool())
    registry.register(LoadSkillTool())
    registry.register(ProposeMemoryTool())
    registry.register(ReadFileTool())
    registry.register(RunPreflightTool())
    registry.register(SearchWebTool())
    registry.register(SubagentAnalyzeTool())
    registry.register(WorkspaceSearchTool())
    registry.register(WriteFileTool())
    register_plugin_tools(registry, root=state_root() / "agent_core" / "plugins")
    return registry


__all__ = [
    "AgentToolContext",
    "AgentToolDispatcher",
    "AgentToolExecutor",
    "AgentToolRegistry",
    "AgentToolSpec",
    "ToolsetExposure",
    "build_default_tool_registry",
]
