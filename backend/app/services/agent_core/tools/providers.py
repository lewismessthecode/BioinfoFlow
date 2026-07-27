from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Protocol

from app.services.agent_core.tools.execution import ExecuteShellTool
from app.services.agent_core.tools.collaboration import COLLABORATION_TOOLS
from app.services.agent_core.tools.files import (
    EditFileTool,
    WriteFileTool,
)
from app.services.agent_core.tools.interaction import AskUserTool, ExitPlanModeTool
from app.services.agent_core.tools.memory import ListMemoriesTool, ProposeMemoryTool
from app.services.agent_core.tools.platform import (
    BindProjectWorkflowTool,
    CancelRunTool,
    CleanupRunTool,
    CreateProjectTool,
    CreateWorkflowTool,
    DeleteProjectTool,
    DeleteRunTool,
    DeleteWorkflowTool,
    GetProjectTool,
    GetRunLogsTool,
    GetRunTool,
    GetWorkflowTool,
    InspectRunTool,
    InspectWorkflowTool,
    ListProjectWorkflowsTool,
    ListProjectsTool,
    ListRunsTool,
    ListWorkflowsTool,
    PinProjectWorkflowTool,
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
from app.services.agent_core.tools.remote import (
    RemoteConnectionsListTool,
    RemoteExecTool,
    RemoteListDirTool,
    RemoteReadFileTool,
)
from app.services.agent_core.tools.skills import (
    ListPluginsTool,
    ListSkillsTool,
    LoadSkillTool,
)
from app.services.agent_core.tools.specs import AgentTool
from app.services.agent_core.tools.tasks import TodoWriteTool
from app.services.agent_core.tools.web import SearchWebTool


class AgentToolProvider(Protocol):
    def tools(self) -> Iterable[AgentTool]:
        """Return tools in a deterministic registration order."""


@dataclass(frozen=True)
class StaticAgentToolProvider:
    _tools: tuple[AgentTool, ...]

    def tools(self) -> Iterable[AgentTool]:
        return self._tools


def default_tool_providers() -> tuple[AgentToolProvider, ...]:
    return (
        StaticAgentToolProvider(
            (
                WriteFileTool(),
                EditFileTool(),
                ExecuteShellTool(),
            )
        ),
        StaticAgentToolProvider(
            (
                ListProjectsTool(),
                GetProjectTool(),
                CreateProjectTool(),
                UpdateProjectTool(),
                DeleteProjectTool(),
                ListProjectWorkflowsTool(),
                BindProjectWorkflowTool(),
                UnbindProjectWorkflowTool(),
                PinProjectWorkflowTool(),
                ListWorkflowsTool(),
                InspectWorkflowTool(),
                GetWorkflowTool(),
                CreateWorkflowTool(),
                UpdateWorkflowTool(),
                DeleteWorkflowTool(),
                WorkflowFormSpecTool(),
                WorkflowDagTool(),
                WorkflowSourceTool(),
                ListRunsTool(),
                InspectRunTool(),
                GetRunTool(),
                GetRunLogsTool(),
                SubmitRunTool(),
                CancelRunTool(),
                RetryRunTool(),
                ResumeRunTool(),
                CleanupRunTool(),
                DeleteRunTool(),
                RunOutputsTool(),
                RunDagTool(),
                RunAuditTool(),
                SchedulerStatusTool(),
                SchedulerResourcesTool(),
            )
        ),
        StaticAgentToolProvider(
            (
                RemoteConnectionsListTool(),
                RemoteExecTool(),
                RemoteReadFileTool(),
                RemoteListDirTool(),
            )
        ),
        StaticAgentToolProvider((SearchWebTool(),)),
        StaticAgentToolProvider(
            (
                ListMemoriesTool(),
                ProposeMemoryTool(),
                ListSkillsTool(),
                LoadSkillTool(),
                ListPluginsTool(),
                TodoWriteTool(),
                AskUserTool(),
                ExitPlanModeTool(),
                *COLLABORATION_TOOLS,
            )
        ),
    )
