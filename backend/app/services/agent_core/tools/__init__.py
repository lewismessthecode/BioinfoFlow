from app.services.agent_core.tools.bio import (
    BuildImageCardTool,
    BuildWorkflowCardTool,
    DiagnoseRunTool,
    InterpretResultsTool,
    RunPreflightTool,
)
from app.services.agent_core.tools.dispatcher import AgentToolDispatcher
from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.memory import ListMemoriesTool, ProposeMemoryTool
from app.services.agent_core.tools.platform import (
    GetRunLogsTool,
    ListImagesTool,
    ListProjectsTool,
    ListRunsTool,
    ListWorkflowsTool,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.skills import (
    ListPluginsTool,
    ListSkillsTool,
    LoadSkillTool,
)
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec


def build_default_tool_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()
    registry.register(BuildImageCardTool())
    registry.register(BuildWorkflowCardTool())
    registry.register(DiagnoseRunTool())
    registry.register(ExecuteShellTool())
    registry.register(InterpretResultsTool())
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
    registry.register(RunPreflightTool())
    return registry


__all__ = [
    "AgentToolContext",
    "AgentToolDispatcher",
    "AgentToolRegistry",
    "AgentToolSpec",
    "build_default_tool_registry",
]
