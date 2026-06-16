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
from app.services.agent_core.tools.interaction import AskUserTool, ExitPlanModeTool
from app.services.agent_core.tools.memory import ListMemoriesTool, ProposeMemoryTool
from app.services.agent_core.tools.search import GlobTool, GrepTool
from app.services.agent_core.tools.tasks import TodoWriteTool
from app.services.agent_core.tools.platform import (
    BindProjectWorkflowTool,
    BuildImageTool,
    CancelRunTool,
    CleanupRunTool,
    CreateProjectTool,
    CreateWorkflowTool,
    DeleteImageTool,
    DeleteProjectTool,
    DeleteRunTool,
    DeleteWorkflowTool,
    GetImageTool,
    GetProjectTool,
    GetRunLogsTool,
    GetRunTool,
    GetWorkflowTool,
    ListImagesTool,
    ListProjectWorkflowsTool,
    ListProjectsTool,
    ListRunsTool,
    ListWorkflowsTool,
    PinProjectWorkflowTool,
    PullImageTool,
    RetryRunTool,
    ResumeRunTool,
    RunAuditTool,
    RunDagTool,
    RunOutputsTool,
    SchedulerResourcesTool,
    SchedulerStatusTool,
    SubmitRunTool,
    UnbindProjectWorkflowTool,
    UpdateProjectTool,
    UpdateWorkflowTool,
    WorkflowDagTool,
    WorkflowFormSpecTool,
    WorkflowSourceTool,
)
from app.services.agent_core.tools.registry import AgentToolRegistry
from app.services.agent_core.tools.skills import (
    ListPluginsTool,
    ListSkillsTool,
    LoadSkillTool,
)
from app.services.agent_core.tools.specs import AgentToolContext, AgentToolSpec
from app.services.agent_core.tools.subagents import SubagentAnalyzeTool, TaskTool
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
    registry.register(GrepTool())
    registry.register(GlobTool())
    registry.register(ListMemoriesTool())
    registry.register(ProposeMemoryTool())
    registry.register(ListSkillsTool())
    registry.register(LoadSkillTool())
    registry.register(ListPluginsTool())

    # ── interaction + task-management tools ────────────────────────────────
    registry.register(TodoWriteTool())
    registry.register(AskUserTool())
    registry.register(ExitPlanModeTool())

    # ── platform tools (read + side-effecting "tentacles") ─────────────────
    registry.register(ListProjectsTool())
    registry.register(GetProjectTool())
    registry.register(CreateProjectTool())
    registry.register(UpdateProjectTool())
    registry.register(DeleteProjectTool())
    registry.register(ListProjectWorkflowsTool())
    registry.register(BindProjectWorkflowTool())
    registry.register(UnbindProjectWorkflowTool())
    registry.register(PinProjectWorkflowTool())
    registry.register(ListWorkflowsTool())
    registry.register(GetWorkflowTool())
    registry.register(CreateWorkflowTool())
    registry.register(UpdateWorkflowTool())
    registry.register(DeleteWorkflowTool())
    registry.register(WorkflowFormSpecTool())
    registry.register(WorkflowDagTool())
    registry.register(WorkflowSourceTool())
    registry.register(ListImagesTool())
    registry.register(GetImageTool())
    registry.register(PullImageTool())
    registry.register(BuildImageTool())
    registry.register(DeleteImageTool())
    registry.register(ListRunsTool())
    registry.register(GetRunTool())
    registry.register(GetRunLogsTool())
    registry.register(SubmitRunTool())
    registry.register(CancelRunTool())
    registry.register(RetryRunTool())
    registry.register(ResumeRunTool())
    registry.register(CleanupRunTool())
    registry.register(DeleteRunTool())
    registry.register(RunOutputsTool())
    registry.register(RunDagTool())
    registry.register(RunAuditTool())
    registry.register(SchedulerStatusTool())
    registry.register(SchedulerResourcesTool())

    # ── web + delegation tools ─────────────────────────────────────────────
    registry.register(SearchWebTool())
    registry.register(FetchWebPageTool())
    registry.register(SubagentAnalyzeTool())
    registry.register(TaskTool())

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
