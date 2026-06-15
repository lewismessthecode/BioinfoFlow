from app.path_layout import state_root
from app.services.agent_core.plugins import register_plugin_tools
from app.services.agent_core.tools.dispatcher import AgentToolDispatcher
from app.services.agent_core.tools.executor import AgentToolExecutor
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.files import (
    EditFileTool,
    ReadFileTool,
    WriteFileTool,
)
from app.services.agent_core.tools.memory import ListMemoriesTool, ProposeMemoryTool
from app.services.agent_core.tools.platform import (
    BuildImageTool,
    CancelRunTool,
    CreateWorkflowTool,
    GetRunLogsTool,
    ListImagesTool,
    ListProjectsTool,
    ListRunsTool,
    ListWorkflowsTool,
    PullImageTool,
    RetryRunTool,
    SubmitRunTool,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
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
    """Register every tool in a deterministic, grouped order.

    Registration order is grouped (built-ins → platform → web/subagent) for
    cache-key stability. Exposure is decided separately by ``ToolsetExposure``:
    registration is not exposure. The capable "execution" toolset exposes all of
    these; the read-only "default"/"worker" policies expose a safe subset.
    """
    registry = AgentToolRegistry()

    # ── built-in file + shell + memory tools ───────────────────────────────
    registry.register(ReadFileTool())
    registry.register(WriteFileTool())
    registry.register(EditFileTool())
    registry.register(ExecuteShellTool())
    registry.register(ListMemoriesTool())
    registry.register(ProposeMemoryTool())
    registry.register(ListSkillsTool())
    registry.register(LoadSkillTool())
    registry.register(ListPluginsTool())

    # ── platform tools (read + side-effecting "tentacles") ─────────────────
    registry.register(ListProjectsTool())
    registry.register(ListWorkflowsTool())
    registry.register(CreateWorkflowTool())
    registry.register(ListImagesTool())
    registry.register(PullImageTool())
    registry.register(BuildImageTool())
    registry.register(ListRunsTool())
    registry.register(GetRunLogsTool())
    registry.register(SubmitRunTool())
    registry.register(CancelRunTool())
    registry.register(RetryRunTool())

    # ── web + delegation tools ─────────────────────────────────────────────
    registry.register(SearchWebTool())
    registry.register(FetchWebPageTool())
    registry.register(SubagentAnalyzeTool())

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
