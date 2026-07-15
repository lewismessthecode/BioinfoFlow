import type * as React from "react"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { AgentWorkbench } from "@/components/bioinfoflow/agent-runtime/agent-workbench"
import type {
  AgentRuntimeArtifact,
  AgentRuntimeEvent,
  AgentRuntimeSession,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"
import { writeAgentTurnPolicy } from "@/lib/agent-runtime/turn-policy"

const useAgentRuntimeMock = vi.fn()
const useLlmSettingsMock = vi.fn()
const useIsMobileMock = vi.fn(() => false)
const setNavbarActionsMock = vi.fn()
const apiRequestMock = vi.fn()
let workspaceProjectsMock: Array<{
  id: string
  name: string
  storage_mode?: "managed" | "external" | "remote"
  remote_connection_id?: string | null
}> = []

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string, values?: Record<string, string | number>) => {
    const labels: Record<string, string> = {
      welcomeTitle: "What should Bioinfoflow help you do today?",
      composerPlaceholder: "Message Bioinfoflow...",
      attach: "Attach or add context",
      send: "Send message",
      stop: "Stop response",
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      "statusLine.running": "Working...",
      "responseActions.copy": "Copy response",
      "responseActions.retry": "Retry response",
      showThinking: "Show thinking",
      hideThinking: "Hide thinking",
      toolCalls: "Tool calls",
      "activity.groups.read": "Read data",
      "activity.summary.read": "Read 1 source",
      approve: "Approve",
      reject: "Reject",
      "approval.state.approved": "Approved, resuming",
      "approval.jumpToDecision": "Needs confirmation · Jump",
      "decision.focusedNext": "Decision submitted. Moved to the next request.",
      "decision.focusedComposer": "Decision submitted. Focus returned to the composer.",
      "turnStatus.running": "Working",
      "turnStatus.queued": "Queued",
      "turnStatus.completed": "Done",
      "sidecar.title": "Workspace",
      "sidecar.close": "Close workspace panel",
      "sidecar.collapse": "Collapse workspace panel",
      "sidecar.expand": "Open workspace panel",
      "sidecar.files": "Files",
      "sidecar.runs": "Runs",
      "sidecar.tools": "Tools",
      "sidecar.artifacts": "Artifacts",
      "sidecar.active": "Active",
      "sidecar.progress": "Progress",
      "sidecar.currentThinking": "Current thinking",
      "sidecar.currentToolCalls": "Current tool calls",
      "sidecar.needsDecision": "Needs your decision",
      "sidecar.noActivity": "No activity yet",
      "tabs.tools": "Tools",
      "tabs.preview": "Preview",
      "tabs.artifacts": "Artifacts",
      "tabs.files": "Files",
      "tabs.browser": "Browser",
      "artifacts.title": "Artifacts",
      "artifacts.count": `${values?.count ?? 0} artifacts`,
      "artifacts.empty": "No artifacts yet.",
      "artifacts.emptyNoSession": "Start a conversation to collect artifacts.",
      "artifacts.emptyNoSessionDescription": "Generated files will open here.",
      "artifacts.emptyRunningDescription": "Files created by the agent will appear here.",
      "artifacts.loadFailed": "Could not load artifacts.",
      "artifacts.loadFailedDescription": "Refresh the panel and try again.",
      "artifacts.retry": "Retry",
      "files.title": "Files",
      "browser.title": "Browser",
      "browser.empty": "Enter a URL to preview a page.",
      "environment.open": "Open environment",
      "environment.close": "Close environment",
      "environment.title": "Environment",
      "environment.changes": "Changes",
      "environment.filesChanged": "1 file changed",
      "environment.worktree": "Worktree",
      "environment.session": "Session",
      "environment.pendingSession": "Session pending",
      "environment.model": "Model",
      "environment.progress": "Progress",
      "environment.activity": "Subagents and tools",
      "environment.sources": "Sources",
      "environment.none": "None",
      "attachMenu.attachFiles": "Attach files",
      "attachMenu.browseProjectFiles": "Browse project files",
      "attachMenu.referenceRun": "Reference a run",
      "attachMenu.runPreflight": "Run preflight",
      "attachMenu.diagnoseRun": "Diagnose run",
      "attachMenu.comingSoon": "Coming soon",
      "permission.label": "Permission mode",
      "permission.options.ask_each_action.label": "Request approval",
      "permission.options.ask_each_action.description": "Ask before side-effecting actions.",
      "permission.options.guarded_auto.label": "Approve for me",
      "permission.options.guarded_auto.description": "Run low-risk actions automatically.",
      "permission.options.bypass.label": "Full access",
      "permission.options.bypass.description": "Run non-critical actions automatically.",
      "permission.boundary.local": "Local actions remain inside the active Bioinfoflow sandbox.",
      "permission.boundary.remote": "SSH actions use the remote account and server policy; the working folder is not a sandbox.",
      "permission.safetyFloor": "Critical actions remain blocked in every mode.",
      "permission.status.updating": "Updating permission mode...",
      "permission.status.updated": "Permission mode updated for future operations.",
      "permission.status.reconciled": `${values?.affected ?? 0} waiting operations approved; ${values?.excluded ?? 0} excluded.`,
      "permission.status.failed": `Could not update permission mode: ${values?.error ?? ""}`,
      "permission.retry": "Retry permission update",
      "permission.confirm.title": "Update permission mode?",
      "permission.confirm.description": `${values?.eligible ?? 0} waiting tool operations can be approved; ${values?.excluded ?? 0} interactions stay pending.`,
      "permission.confirm.futureOnly": "Only update future operations",
      "permission.confirm.futureOnlyDescription": "Current waiting operations still need your decision.",
      "permission.confirm.approvePending": `Update and approve ${values?.count ?? 0} waiting tools`,
      "permission.confirm.approvePendingDescription": "Questions and plan reviews are never auto-approved.",
      "permission.confirm.cancel": "Cancel",
      allTargets: "All targets",
      manual: "Manual",
      menuTitle: "Local / Remote",
      manage: "Manage SSH hosts",
      "local.label": "Local",
      "runtimeLocation.local.label": "Local",
      "local.description": "Run in this Bioinfoflow workspace",
      localBadge: "Local",
      "remote.label": "Remote",
      emptyRemoteHosts: "No remote hosts configured.",
      loadFailed: "Could not load remote hosts.",
      "status.online": "Online",
      "status.offline": "Offline",
      "status.error": "Connection error",
      "status.unknown": "Not tested",
      selectedAutoAria: `Execution targets: Auto, ${values?.target ?? ""}`,
      selectedManualAria: `Execution targets: Manual, ${values?.target ?? ""}`,
      targetCount: `${values?.count ?? 0} selected`,
      "tokenUsage.label": "Tokens",
      "tokenUsage.display": `${values?.value ?? ""} tokens`,
      "tokenUsage.compactDisplay": `${values?.value ?? ""}`,
      "tokenUsage.aria": `${values?.total ?? ""} tokens used in this session. ${values?.input ?? ""} input, ${values?.output ?? ""} output.`,
      "tokenUsage.title": "Context window",
      "tokenUsage.used": "Used",
      "tokenUsage.remaining": "remaining",
      "tokenUsage.input": "Input",
      "tokenUsage.output": "Output",
      "tokenUsage.cached": "Cached",
      "tokenUsage.reasoning": "Reasoning",
      "tokenUsage.window": "Window",
      "tokenUsage.maxOutput": "Max output",
      "skills.menuTitle": "Skills",
      "skills.loading": "Loading skills...",
      "skills.empty": "No skills found.",
      "skills.noMatches": "No matching skills.",
      "skills.loadFailed": "Could not load skills.",
      "skills.remove": `Remove ${values?.name ?? ""}`,
      "skills.activeForNextTurn": "Skills",
      "starterSuggestions.checkWorkflow.prompt": "Check this workflow before I run it",
      "starterSuggestions.chooseInputs.prompt": "Help me choose analysis inputs",
      "starterSuggestions.reviewFailure.prompt": "Review the latest failed run",
      "starterSuggestions.prepareRun.prompt": "Prepare a run from @workflow",
      "commandHints.workflow.prefix": "Use",
      "commandHints.workflow.suffix": "to attach workflow context",
      "commandHints.skills.prefix": "Type",
      "commandHints.skills.suffix": "to choose one or more skills",
      "commandHints.mode.prefix": "Press",
      "commandHints.mode.suffix": "to switch plan and act mode",
      "workflowContext.label": "Workflow context",
      auto: "Auto",
      configure: "Configure providers",
      noProviders: "No model available",
      searchModels: "Search models...",
    }
    return labels[key] ?? key
  },
}))

vi.mock("next/link", () => ({
  default: ({
    children,
    href,
    ...props
  }: React.AnchorHTMLAttributes<HTMLAnchorElement> & { href: string }) => (
    <a href={href} {...props}>
      {children}
    </a>
  ),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}))

vi.mock("@/hooks/use-agent-runtime", () => ({
  useAgentRuntime: (...args: unknown[]) => useAgentRuntimeMock(...args),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: () => useLlmSettingsMock(),
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => useIsMobileMock(),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useOptionalWorkspaceShell: () => ({
    setNavbarActions: setNavbarActionsMock,
    projects: workspaceProjectsMock,
  }),
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => (
    <span aria-hidden="true" data-provider={provider} />
  ),
}))

const baseSession: AgentRuntimeSession = {
  id: "session-1",
  workspace_id: "workspace-1",
  user_id: "user-1",
  role_profile: "bioinformatician",
  permission_mode: "guarded_auto",
  automation_mode: "assisted",
  runtime_mode: "api",
  status: "active",
  created_at: "2026-06-09T00:00:00Z",
  updated_at: "2026-06-09T00:00:00Z",
}

const baseTurn: AgentRuntimeTurn = {
  id: "turn-1",
  session_id: "session-1",
  project_id: null,
  workspace_id: "workspace-1",
  user_id: "user-1",
  input_text: "Analyze these FASTQ files.",
  status: "completed",
  model_selection: null,
  final_text: "The files look ready.",
  token_usage: null,
  termination_reason: null,
  loop_state: null,
  iteration_count: 1,
  budget_snapshot: null,
  created_at: "2026-06-09T00:00:00Z",
  updated_at: "2026-06-09T00:00:00Z",
}

const priorTodoArtifact: AgentRuntimeArtifact = {
  id: "artifact-todo-1",
  session_id: "session-1",
  turn_id: "turn-1",
  action_id: "action-todo-1",
  type: "todo_list",
  title: "Tasks",
  summary: null,
  payload: {
    todos: [{ content: "Old task", status: "in_progress", activeForm: "Working old task" }],
  },
  file_path: null,
  resource_ref: null,
  created_at: "2026-06-09T00:00:03Z",
  updated_at: "2026-06-09T00:00:03Z",
}

const waitingDecisionEvent: AgentRuntimeEvent = {
  id: "event-1",
  session_id: "session-1",
  turn_id: "turn-1",
  seq: 1,
  type: "action.waiting_decision",
  payload: { action_id: "action-1", name: "files__write" },
  visibility: "user",
  schema_version: 1,
  created_at: "2026-06-09T00:00:00Z",
  updated_at: "2026-06-09T00:00:00Z",
}

function setupRuntime({
  session = null,
  turns = [],
  events = [],
  status = "idle",
  send = vi.fn(),
  permissionMode = "guarded_auto",
  setPermissionMode = vi.fn(),
  permissionUpdate = {
    status: "idle" as const,
    mode: null,
    pendingStrategy: null,
    reconciliation: null,
    error: null,
  },
}: {
  session?: AgentRuntimeSession | null
  turns?: AgentRuntimeTurn[]
  events?: AgentRuntimeEvent[]
  status?: "idle" | "loading" | "running" | "error"
  send?: ReturnType<typeof vi.fn>
  permissionMode?: "ask_each_action" | "guarded_auto" | "bypass"
  setPermissionMode?: ReturnType<typeof vi.fn>
  permissionUpdate?: {
    status: "idle" | "pending" | "success" | "error"
    mode: "ask_each_action" | "guarded_auto" | "bypass" | null
    pendingStrategy: "future_only" | "approve_pending_tools" | null
    reconciliation: {
      affected_count: number
      excluded_count: number
      already_resolved_count: number
    } | null
    error: string | null
  }
} = {}) {
  useAgentRuntimeMock.mockReturnValue({
    state: {
      session,
      turns,
      events,
      timeline: buildAgentRuntimeTimeline(turns, events),
      status,
      error: null,
    },
    setActiveSessionId: vi.fn(),
    send,
    interrupt: vi.fn(),
    decideAction: vi.fn(),
    permissionMode,
    setPermissionMode,
    permissionUpdate,
    retryPermissionModeUpdate: vi.fn(),
  })
}

const autoExecutionScope = { mode: "auto" }

function manualRemoteExecutionScope(connectionId: string) {
  return {
    mode: "manual",
    selected_targets: [
      {
        kind: "remote_ssh",
        type: "remote_ssh",
        connection_id: connectionId,
        remote_connection_id: connectionId,
      },
    ],
  }
}

const manualLocalExecutionScope = {
  mode: "manual",
  selected_targets: [{ kind: "local", type: "local" }],
}

describe("AgentWorkbench", () => {
  beforeEach(() => {
    useAgentRuntimeMock.mockReset()
    useLlmSettingsMock.mockReset()
    useIsMobileMock.mockReset()
    useIsMobileMock.mockReturnValue(false)
    setNavbarActionsMock.mockReset()
    workspaceProjectsMock = []
    apiRequestMock.mockReset()
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") return new Promise(() => {})
      if (path === "/agent/skills") return Promise.resolve({ data: { skills: [] } })
      if (path.startsWith("/agent/fs/tree")) {
        return Promise.resolve({ path: "/workspace/project-1", entries: [] })
      }
      return Promise.resolve({ data: [] })
    })
    useLlmSettingsMock.mockReturnValue({
      models: [],
      selectedModel: null,
      isLoading: false,
      setSelectedModel: vi.fn(),
    })
    setupRuntime()
    window.localStorage.clear()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it("renders the new chat welcome with a centered composer", () => {
    render(<AgentWorkbench />)

    expect(
      screen.getByText("What should Bioinfoflow help you do today?"),
    ).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "center",
    )
    expect(screen.queryByText("Agent Harness")).not.toBeInTheDocument()
    expect(screen.queryByText("Start from the runtime")).not.toBeInTheDocument()
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-sidecar-column")).toHaveAttribute(
      "aria-hidden",
      "true",
    )
  })

  it("renders restrained starter suggestions and command discovery hints in the empty composer", () => {
    render(<AgentWorkbench />)

    expect(screen.getByTestId("agent-starter-suggestions")).toBeInTheDocument()
    expect(
      screen.getByRole("button", { name: "Check this workflow before I run it" }),
    ).toHaveClass("focus-visible:ring-1")
    expect(
      screen.getByRole("button", { name: "Help me choose analysis inputs" }),
    ).toBeInTheDocument()
    expect(screen.queryByText("Validate workflow inputs")).not.toBeInTheDocument()
    const hints = screen.getByTestId("agent-command-discovery-hints")
    expect(hints).toHaveClass("agent-center-stage")
    expect(within(hints).getByText("@workflow").tagName).toBe("KBD")
    expect(within(hints).getByText("Use")).toBeInTheDocument()
    expect(within(hints).getByText("to attach workflow context")).toBeInTheDocument()
    expect(within(hints).getByLabelText("Use @workflow to attach workflow context")).toBe(
      within(hints).getByText("Use").parentElement,
    )
    expect(within(hints).queryByText("/")).not.toBeInTheDocument()
  })

  it("keeps rotating command discovery hints visible after the text swap", () => {
    vi.useFakeTimers()
    render(<AgentWorkbench />)

    const hints = screen.getByTestId("agent-command-discovery-hints")
    expect(within(hints).getByText("@workflow")).toBeInTheDocument()

    act(() => {
      vi.advanceTimersByTime(5200 + 150 + 16)
    })

    expect(within(hints).getByText("/")).toBeInTheDocument()
    expect(within(hints).getByText("Type")).toBeInTheDocument()
    expect(within(hints).getByLabelText("Type / to choose one or more skills")).toBe(
      within(hints).getByText("Type").parentElement,
    )
  })

  it("fills the centered composer from a starter suggestion", () => {
    render(<AgentWorkbench />)

    fireEvent.click(
      screen.getByRole("button", { name: "Check this workflow before I run it" }),
    )

    expect(screen.getByPlaceholderText("Message Bioinfoflow...")).toHaveValue(
      "Check this workflow before I run it",
    )
  })

  it("keeps active project context out of the centered composer", () => {
    workspaceProjectsMock = [
      {
        id: "project-1",
        name: "Mitochondrial variant review",
        storage_mode: "managed",
      },
    ]

    render(<AgentWorkbench projectId="project-1" />)

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-presentation",
      "center",
    )
    expect(screen.queryByText("Mitochondrial variant review")).not.toBeInTheDocument()
  })

  it("registers the runtime sidecar toggle with the navbar action group", () => {
    render(<AgentWorkbench />)

    expect(setNavbarActionsMock).toHaveBeenCalled()
    const lastCall = setNavbarActionsMock.mock.calls.at(-1)
    expect(lastCall?.[0]).toBeTruthy()
    expect(
      screen.queryByRole("button", { name: "Open workspace panel" }),
    ).not.toBeInTheDocument()
  })

  it("opens the desktop workspace drawer to artifacts from the app top chrome", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    const drawer = screen.getByTestId("artifact-panel")
    expect(drawer).toBeInTheDocument()
    expect(screen.queryByTestId("agent-workbench-top-actions")).not.toBeInTheDocument()
    expect(within(drawer).queryByTestId("agent-sidecar-tab-strip")).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-sidecar-column")).toHaveStyle({
      width: "600px",
    })
    expect(
      screen.getByRole("separator", { name: "Resize right sidebar" }),
    ).toBeInTheDocument()
    const navbarActions = screen.getByTestId("agent-navbar-actions")
    expect(
      within(navbarActions).getByRole("tablist", { name: "Workspace" }),
    ).toBeInTheDocument()
    expect(within(navbarActions).getByRole("tab", { name: "Artifacts" })).toHaveAttribute(
      "data-active",
      "true",
    )
    expect(within(navbarActions).queryByRole("tab", { name: "Tools" })).not.toBeInTheDocument()
  })

  it("keeps agent actions and workspace tabs in the single app top chrome while the desktop drawer is open", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(setNavbarActionsMock.mock.calls.at(-1)?.[0]).toBeTruthy()
    })
    navbarRender.rerender(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    expect(screen.queryByTestId("agent-workbench-top-actions")).not.toBeInTheDocument()
    const navbarActions = screen.getByTestId("agent-navbar-actions")
    expect(
      within(navbarActions).getByRole("tablist", { name: "Workspace" }),
    ).toBeInTheDocument()
    expect(within(navbarActions).getByRole("tab", { name: "Artifacts" })).toBeInTheDocument()
    expect(within(navbarActions).getByRole("tab", { name: "Files" })).toBeInTheDocument()
    expect(within(navbarActions).getByRole("tab", { name: "Browser" })).toBeInTheDocument()
    expect(
      within(navbarActions).getByRole("button", { name: "Open environment" }),
    ).toBeInTheDocument()
    expect(
      within(navbarActions).getByRole("button", { name: "Collapse workspace panel" }),
    ).toBeInTheDocument()
  })

  it("returns focus to the navbar workspace toggle after collapsing the desktop drawer", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    navbarRender.rerender(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )
    await act(async () => {
      fireEvent.click(
        within(screen.getByTestId("agent-navbar-actions")).getByRole("button", {
          name: "Collapse workspace panel",
        }),
      )
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(setNavbarActionsMock.mock.calls.at(-1)?.[0]).toBeTruthy()
    })
    navbarRender.rerender(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    await waitFor(() => {
      expect(
        within(screen.getByTestId("agent-navbar-actions")).getByRole("button", {
          name: "Open workspace panel",
        }),
      ).toHaveFocus()
    })
  })

  it("moves focus to the environment panel when opening it from the app top chrome", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <div data-testid="agent-navbar-actions">
        {setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}
      </div>,
    )

    fireEvent.click(
      within(screen.getByTestId("agent-navbar-actions")).getByRole("button", {
        name: "Open environment",
      }),
    )

    const floatingPanel = await screen.findByTestId("agent-environment-floating-panel")
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    await waitFor(() => {
      expect(floatingPanel).toHaveFocus()
    })
  })

  it("keeps the draft composer centered when the desktop workspace drawer is open", async () => {
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "center",
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    expect(screen.getByTestId("artifact-panel")).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "center",
    )
    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-presentation",
      "center",
    )
    const suggestions = within(screen.getByTestId("agent-starter-suggestions")).getAllByRole(
      "button",
    )
    expect(suggestions).toHaveLength(3)
    expect(screen.queryByRole("button", { name: "Prepare a run from @workflow" }))
      .not.toBeInTheDocument()
  })

  it("resizes the desktop workspace drawer and stores the preferred width", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    const sidecar = screen.getByTestId("agent-sidecar-column")
    const resizer = screen.getByRole("separator", { name: "Resize right sidebar" })
    expect(resizer).toHaveAttribute("aria-valuemin", "380")
    expect(resizer).toHaveAttribute("aria-valuemax", "760")
    expect(resizer).toHaveAttribute("aria-valuenow", "600")
    expect(resizer).toHaveClass("w-2")
    expect(resizer.firstElementChild).toHaveClass("w-px")

    fireEvent.keyDown(resizer, { key: "ArrowLeft" })
    expect(sidecar).toHaveStyle({ width: "616px" })
    expect(resizer).toHaveAttribute("aria-valuenow", "616")
    expect(window.localStorage.getItem("agent-sidecar-width")).toBe("616")

    fireEvent.mouseDown(resizer, { clientX: 500 })
    fireEvent.mouseMove(document, { clientX: 460 })
    fireEvent.mouseUp(document)

    await waitFor(() => {
      expect(sidecar).toHaveStyle({ width: "656px" })
    })
    expect(window.localStorage.getItem("agent-sidecar-width")).toBe("656")
  })

  it("clamps the desktop workspace drawer to preserve the chat column on narrow desktop widths", async () => {
    const rectSpy = vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      width: 724,
      height: 0,
      top: 0,
      right: 724,
      bottom: 0,
      left: 0,
      toJSON: () => ({}),
    } as DOMRect)

    try {
      window.localStorage.setItem("agent-sidecar-width", "760")
      setupRuntime({ session: baseSession })
      render(<AgentWorkbench projectId="project-1" />)
      const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
      render(<>{navbarActions}</>)

      await act(async () => {
        fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
        await Promise.resolve()
      })

      await waitFor(() => {
        expect(screen.getByTestId("agent-sidecar-column")).toHaveStyle({
          width: "304px",
        })
      })
    } finally {
      rectSpy.mockRestore()
    }
  })

  it("does not reopen the right drawer when starting a new conversation", async () => {
    const workbenchRef = { current: null as React.ElementRef<typeof AgentWorkbench> | null }
    render(<AgentWorkbench ref={workbenchRef} projectId="project-1" />)

    await act(async () => {
      workbenchRef.current?.newConversation()
      await Promise.resolve()
    })

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-sidecar-column")).toHaveAttribute(
      "aria-hidden",
      "true",
    )
  })

  it("resets the workspace tab and browser preview when starting a new conversation", async () => {
    setupRuntime({ session: baseSession })
    const workbenchRef = { current: null as React.ElementRef<typeof AgentWorkbench> | null }
    render(<AgentWorkbench ref={workbenchRef} projectId="project-1" />)
    const navbarRender = render(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    fireEvent.click(screen.getByRole("tab", { name: "Browser" }))
    const input = screen.getByPlaceholderText("browser.urlPlaceholder")
    fireEvent.change(input, { target: { value: "/runs" } })
    fireEvent.click(screen.getByRole("button", { name: "browser.go" }))
    expect(screen.getByTitle("Browser")).toHaveAttribute(
      "src",
      "http://localhost:3000/runs",
    )

    await act(async () => {
      workbenchRef.current?.newConversation()
      await Promise.resolve()
    })

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    expect(screen.getByRole("tab", { name: "Artifacts" })).toHaveAttribute(
      "data-active",
      "true",
    )
    fireEvent.click(screen.getByRole("tab", { name: "Browser" }))
    expect(screen.getByPlaceholderText("browser.urlPlaceholder")).toHaveValue("")
    expect(screen.getByText("Enter a URL to preview a page.")).toBeInTheDocument()
    expect(screen.queryByTitle("Browser")).not.toBeInTheDocument()
  })

  it("preserves the active workspace drawer panel after closing and reopening", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    fireEvent.click(screen.getByRole("tab", { name: "Browser" }))
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )
    expect(screen.getByRole("tab", { name: "Browser" })).toHaveAttribute(
      "data-active",
      "true",
    )

    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Collapse workspace panel" }))
      await Promise.resolve()
    })

    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    expect(screen.getByRole("tab", { name: "Browser" })).toHaveAttribute(
      "data-active",
      "true",
    )
    expect(screen.getByTestId("browser-tab")).toBeInTheDocument()
  })

  it("preserves the browser URL after closing and reopening the drawer", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarRender = render(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    fireEvent.click(screen.getByRole("tab", { name: "Browser" }))
    const input = screen.getByPlaceholderText("browser.urlPlaceholder")
    fireEvent.change(input, { target: { value: "/runs" } })
    fireEvent.click(screen.getByRole("button", { name: "browser.go" }))
    expect(screen.getByTitle("Browser")).toHaveAttribute(
      "src",
      "http://localhost:3000/runs",
    )

    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Collapse workspace panel" }))
      await Promise.resolve()
    })

    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )
    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })
    navbarRender.rerender(
      <>{setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement}</>,
    )

    expect(screen.getByPlaceholderText("browser.urlPlaceholder")).toHaveValue(
      "http://localhost:3000/runs",
    )
    expect(screen.getByTitle("Browser")).toHaveAttribute(
      "src",
      "http://localhost:3000/runs",
    )
  })

  it("opens environment information as a floating workbench panel", async () => {
    setupRuntime({
      session: baseSession,
      events: [
        {
          ...waitingDecisionEvent,
          id: "event-change",
          type: "action.completed",
          payload: {
            action_id: "a1",
            name: "files__write",
            result: {
              path: "/workspace/project-1/workflow.nf",
              additions: 12,
              deletions: 3,
            },
          },
        },
      ],
    })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    fireEvent.click(screen.getByRole("button", { name: "Open environment" }))

    const floatingPanel = await screen.findByTestId("agent-environment-floating-panel")
    expect(floatingPanel).toContainElement(screen.getByTestId("agent-environment-card"))
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getByText("Environment")).toBeInTheDocument()
    expect(screen.getByText("+12")).toBeInTheDocument()
    expect(screen.getByText("-3")).toBeInTheDocument()
  })

  it("closes the floating environment panel when the right drawer opens", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    const navbarRender = render(<>{navbarActions}</>)

    fireEvent.click(screen.getByRole("button", { name: "Open environment" }))
    expect(await screen.findByTestId("agent-environment-floating-panel")).toBeInTheDocument()

    const updatedNavbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    navbarRender.rerender(<>{updatedNavbarActions}</>)

    act(() => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
    })

    expect(screen.getByTestId("artifact-panel")).toBeInTheDocument()
    expect(screen.getByTestId("agent-sidecar-column")).toHaveAttribute(
      "aria-hidden",
      "false",
    )
    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/artifacts")
    })
    expect(screen.queryByTestId("agent-environment-floating-panel")).not.toBeInTheDocument()
    expect(
      within(screen.getByTestId("artifact-panel")).queryByTestId("agent-environment-card"),
    ).not.toBeInTheDocument()
  })

  it("uses compact composer controls while the right drawer is open", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    const navbarRender = render(<>{navbarActions}</>)

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-compact-controls",
      "false",
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-compact-controls",
      "true",
    )

    const updatedNavbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    navbarRender.rerender(<>{updatedNavbarActions}</>)

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Collapse workspace panel" }))
      await Promise.resolve()
    })

    expect(screen.getByTestId("agent-composer")).not.toHaveAttribute(
      "data-compact-controls",
      "true",
    )
  })

  it("opens the workspace panel as a mobile overlay", async () => {
    useIsMobileMock.mockReturnValue(true)
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-sidecar-column")).toHaveAttribute(
      "aria-hidden",
      "true",
    )

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    expect(screen.getByTestId("agent-mobile-sidecar-overlay")).toBeInTheDocument()
    expect(screen.getByRole("dialog", { name: "Workspace" })).toHaveAttribute(
      "aria-modal",
      "true",
    )
    const mobilePanel = screen.getByTestId("artifact-panel")
    expect(mobilePanel).toBeInTheDocument()
    expect(mobilePanel).toHaveClass("flex")
    expect(mobilePanel).not.toHaveClass("hidden")
    expect(screen.getByRole("tab", { name: "Artifacts" })).toHaveAttribute(
      "data-active",
      "true",
    )
    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/artifacts")
    })

    fireEvent.keyDown(screen.getByRole("dialog", { name: "Workspace" }), {
      key: "Escape",
    })
    expect(screen.queryByTestId("agent-mobile-sidecar-overlay")).not.toBeInTheDocument()
  })

  it("closes the mobile workspace dialog before jumping to a pending decision", async () => {
    useIsMobileMock.mockReturnValue(true)
    setupRuntime({
      session: baseSession,
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [waitingDecisionEvent],
      status: "running",
    })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))

    const approvalCard = screen.getByTestId("inline-approval-card")
    approvalCard.scrollIntoView = vi.fn()
    const approveButton = within(approvalCard).getByRole("button", { name: "Approve" })

    fireEvent.click(
      within(screen.getByTestId("artifact-panel")).getByRole("button", {
        name: "Needs confirmation · Jump",
      }),
    )

    await waitFor(() => {
      expect(screen.queryByTestId("agent-mobile-sidecar-overlay")).not.toBeInTheDocument()
      expect(approvalCard.scrollIntoView).toHaveBeenCalled()
      expect(approveButton).toHaveFocus()
    })
  })

  it("moves the composer to the bottom after a turn exists", () => {
    workspaceProjectsMock = [
      {
        id: "project-1",
        name: "Mitochondrial variant review",
        storage_mode: "managed",
      },
    ]
    setupRuntime({ turns: [baseTurn] })

    render(<AgentWorkbench projectId="project-1" />)

    expect(screen.getByText("Analyze these FASTQ files.")).toBeInTheDocument()
    expect(screen.getByText("The files look ready.")).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
    expect(screen.getByTestId("agent-transcript-scroll").className).toContain(
      "[padding-bottom:var(--agent-composer-bottom-space,8rem)]",
    )
    expect(screen.getByTestId("agent-composer")).toHaveAttribute(
      "data-presentation",
      "dock",
    )
    expect(
      screen.queryByText("Mitochondrial variant review"),
    ).not.toBeInTheDocument()
  })

  it("shows cumulative token usage from the loaded session state", async () => {
    setupRuntime({
      session: {
        ...baseSession,
        token_usage_summary: {
          has_token_usage: true,
          input_tokens: 97_000,
          output_tokens: 3_000,
          total_tokens: 100_000,
          context_window: 258_000,
          max_output_tokens: null,
          turns_with_usage: 2,
          raw_totals: {},
        },
      },
      turns: [baseTurn],
    })

    render(<AgentWorkbench />)

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/artifacts")
    })
    expect(
      screen.getByRole("button", {
        name: "100K tokens used in this session. 97K input, 3K output.",
      }),
    ).toHaveTextContent("100K tokens")
  })

  it("retries a completed turn through the existing send path and shows a duplicate optimistic turn", async () => {
    const send = vi.fn(() => new Promise(() => {}))
    setupRuntime({
      turns: [
        {
          ...baseTurn,
          input_parts: [
            { type: "text", text: "Analyze these FASTQ files." },
            {
              kind: "file_ref",
              path: "/workspace/reads.fastq.gz",
              label: "reads.fastq.gz",
              includeContent: true,
            },
          ],
          model_selection: { provider: "openai", model: "gpt-5.4" },
        },
      ],
      send,
    })

    render(<AgentWorkbench projectId="project-1" />)

    fireEvent.click(screen.getByRole("button", { name: "Retry response" }))

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Analyze these FASTQ files.",
        expect.objectContaining({
          inputParts: [
            { type: "text", text: "Analyze these FASTQ files." },
            {
              kind: "file_ref",
              path: "/workspace/reads.fastq.gz",
              label: "reads.fastq.gz",
              includeContent: true,
            },
          ],
          modelSelection: { provider: "openai", model: "gpt-5.4" },
        }),
      ),
    )
    expect(screen.getAllByText("Analyze these FASTQ files.")).toHaveLength(2)
    expect(screen.getByText("Working on it...")).toBeInTheDocument()
  })

  it("keeps an active loading session in the conversation layout", () => {
    setupRuntime({ turns: [], status: "loading" })

    render(<AgentWorkbench activeSessionId="session-1" />)

    expect(
      screen.queryByText("What should Bioinfoflow help you do today?"),
    ).not.toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
    expect(screen.queryByTestId("agent-starter-suggestions")).not.toBeInTheDocument()
    expect(screen.queryByTestId("agent-command-discovery-hints")).not.toBeInTheDocument()
  })

  it("shows an optimistic pending response immediately after submitting the centered composer", () => {
    const send = vi.fn(() => new Promise(() => {}))
    useAgentRuntimeMock.mockReturnValue({
      state: {
        session: null,
        turns: [],
        events: [],
        timeline: [],
        status: "loading",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Plan RNA-seq QC" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
    expect(screen.getByText("Plan RNA-seq QC")).toBeInTheDocument()
    expect(screen.getByText("Working on it...")).toBeInTheDocument()
  })

  it("sends selected slash skills with the next turn", async () => {
    const send = vi.fn(async () => undefined)
    setupRuntime({ send })
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/agent/skills") {
        return Promise.resolve({
          data: {
            skills: [
              {
                name: "nextflow-debugging",
                version: "0.1.0",
                description: "Diagnose failed Nextflow runs.",
                tags: ["nextflow"],
              },
            ],
          },
        })
      }
      if (path === "/connections") return new Promise(() => {})
      return Promise.resolve({ data: [] })
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "/next" } })
    await waitFor(() => expect(screen.getByTestId("agent-skill-option")).toBeInTheDocument())
    fireEvent.click(screen.getByTestId("agent-skill-option"))
    fireEvent.change(input, { target: { value: "Analyze this failed run" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Analyze this failed run",
        expect.objectContaining({ activeSkillNames: ["nextflow-debugging"] }),
      ),
    )
    expect(screen.queryByText("/nextflow-debugging")).not.toBeInTheDocument()
  })

  it("turns @workflow into workflow context for the next turn", async () => {
    const send = vi.fn(async () => undefined)
    setupRuntime({ send })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "@workflow Draft a run plan" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Draft a run plan",
        expect.objectContaining({
          inputParts: [
            { type: "text", text: "Draft a run plan" },
            {
              kind: "workflow_ref",
              project_id: null,
              scope: "global",
            },
          ],
        }),
      ),
    )
  })

  it("interrupts the active turn before sending when the turn policy is interrupt", async () => {
    writeAgentTurnPolicy("interrupt")
    const calls: string[] = []
    const send = vi.fn(async () => {
      calls.push("send")
      return undefined
    })
    const interrupt = vi.fn(async () => {
      calls.push("interrupt")
      return null
    })
    useAgentRuntimeMock.mockReturnValue({
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt,
      decideAction: vi.fn(),
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Switch to Deaf_20" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() => expect(interrupt).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("Switch to Deaf_20", expect.any(Object)),
    )
    expect(calls).toEqual(["interrupt", "send"])
  })

  it("waits for an optimistic in-flight turn to become interruptible before replacement send", async () => {
    writeAgentTurnPolicy("interrupt")
    const calls: string[] = []
    const send = vi.fn((text: string) => {
      calls.push(`send:${text}`)
      return text === "First turn"
        ? new Promise(() => {})
        : Promise.resolve(undefined)
    })
    const interrupt = vi.fn(async () => {
      calls.push("interrupt")
      return null
    })
    const runtime = {
      state: {
        session: baseSession,
        turns: [] as AgentRuntimeTurn[],
        events: [] as AgentRuntimeEvent[],
        timeline: [] as ReturnType<typeof buildAgentRuntimeTimeline>,
        status: "idle" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt,
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const view = render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "First turn" } })
    fireEvent.keyDown(input, { key: "Enter" })
    fireEvent.change(input, { target: { value: "Second turn" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(send).toHaveBeenCalledTimes(1)
    expect(interrupt).not.toHaveBeenCalled()
    expect(screen.getByText("Second turn")).toBeInTheDocument()
    expect(screen.getAllByText("Queued")).toHaveLength(2)

    runtime.state = {
      ...runtime.state,
      turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
      timeline: buildAgentRuntimeTimeline(
        [{ ...baseTurn, id: "running-turn", status: "running" }],
        [],
      ),
      status: "running",
    }
    view.rerender(<AgentWorkbench />)

    await waitFor(() => expect(interrupt).toHaveBeenCalledTimes(1))
    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("Second turn", expect.any(Object)),
    )
    expect(calls).toEqual(["send:First turn", "interrupt", "send:Second turn"])
  })

  it("queues a submitted draft until the active turn finishes when the turn policy is queue", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    const runtime = {
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const view = render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Run Deaf_20 next" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(send).not.toHaveBeenCalled()
    expect(input).toHaveValue("")
    expect(screen.getByText("Run Deaf_20 next")).toBeInTheDocument()
    expect(screen.getByText("Queued")).toBeInTheDocument()
    expect(screen.queryByText("Working on it...")).not.toBeInTheDocument()

    runtime.state = {
      ...runtime.state,
      turns: [{ ...baseTurn, id: "running-turn", status: "completed" }],
      timeline: buildAgentRuntimeTimeline(
        [{ ...baseTurn, id: "running-turn", status: "completed" }],
        [],
      ),
      status: "idle",
    }
    view.rerender(<AgentWorkbench />)

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("Run Deaf_20 next", expect.any(Object)),
    )
  })

  it("drops queued drafts when the active conversation changes", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    const sessionA = { ...baseSession, id: "session-a" }
    const sessionB = { ...baseSession, id: "session-b" }
    const runtime = {
      state: {
        session: sessionA,
        turns: [{ ...baseTurn, id: "running-turn", session_id: "session-a", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", session_id: "session-a", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const view = render(<AgentWorkbench activeSessionId="session-a" />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Belongs to A" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(screen.getByText("Belongs to A")).toBeInTheDocument()

    runtime.state = {
      ...runtime.state,
      session: sessionB,
      turns: [],
      timeline: [],
      status: "idle",
    }
    view.rerender(<AgentWorkbench activeSessionId="session-b" />)

    await waitFor(() => {
      expect(screen.queryByText("Belongs to A")).not.toBeInTheDocument()
    })
    expect(send).not.toHaveBeenCalled()
  })

  it("treats an optimistic in-flight turn as active before backend state catches up", () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn(() => new Promise(() => {}))
    setupRuntime({ session: baseSession, send })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "First turn" } })
    fireEvent.keyDown(input, { key: "Enter" })
    fireEvent.change(input, { target: { value: "Second turn" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(send).toHaveBeenCalledTimes(1)
    expect(screen.getByText("Second turn")).toBeInTheDocument()
    expect(screen.getAllByText("Queued")).toHaveLength(2)
  })

  it("cancels queued drafts when starting a new conversation", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    const runtime = {
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const workbenchRef = { current: null as React.ElementRef<typeof AgentWorkbench> | null }
    const view = render(<AgentWorkbench ref={workbenchRef} />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Do this later" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(screen.getByText("Do this later")).toBeInTheDocument()

    await act(async () => {
      workbenchRef.current?.newConversation()
      await Promise.resolve()
    })

    runtime.state = {
      ...runtime.state,
      turns: [],
      timeline: [],
      status: "idle",
    }
    view.rerender(<AgentWorkbench ref={workbenchRef} />)

    expect(send).not.toHaveBeenCalled()
    expect(screen.queryByText("Do this later")).not.toBeInTheDocument()
  })

  it("clears queued drafts when stopping the active turn", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    const interrupt = vi.fn().mockResolvedValue(null)
    const runtime = {
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt,
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const workbenchRef = { current: null as React.ElementRef<typeof AgentWorkbench> | null }
    const view = render(<AgentWorkbench ref={workbenchRef} />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Do not auto-send" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(screen.getByText("Do not auto-send")).toBeInTheDocument()

    await act(async () => {
      workbenchRef.current?.stop()
      await Promise.resolve()
    })

    runtime.state = {
      ...runtime.state,
      turns: [],
      timeline: [],
      status: "idle",
    }
    view.rerender(<AgentWorkbench ref={workbenchRef} />)

    expect(interrupt).toHaveBeenCalledTimes(1)
    expect(send).not.toHaveBeenCalled()
    expect(screen.queryByText("Do not auto-send")).not.toBeInTheDocument()
  })

  it("keeps multiple queued drafts in FIFO order", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    const runtime = {
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const view = render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Queued A" } })
    fireEvent.keyDown(input, { key: "Enter" })
    fireEvent.change(input, { target: { value: "Queued B" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(send).not.toHaveBeenCalled()
    expect(screen.getByText("Queued A")).toBeInTheDocument()
    expect(screen.getByText("Queued B")).toBeInTheDocument()

    runtime.state = {
      ...runtime.state,
      turns: [{ ...baseTurn, id: "running-turn", status: "completed" }],
      timeline: buildAgentRuntimeTimeline(
        [{ ...baseTurn, id: "running-turn", status: "completed" }],
        [],
      ),
      status: "idle",
    }
    view.rerender(<AgentWorkbench />)

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("Queued A", expect.any(Object)),
    )

    runtime.state = {
      ...runtime.state,
      turns: [],
      timeline: [],
      status: "idle",
    }
    view.rerender(<AgentWorkbench />)

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith("Queued B", expect.any(Object)),
    )
    expect(send.mock.calls.map((call) => call[0])).toEqual(["Queued A", "Queued B"])
  })

  it("keeps the execution scope selected when a draft was queued", async () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") {
        return Promise.resolve({
          data: [
            {
              id: "connection-test-231",
              name: "Test host sz03",
              host: "10.227.5.231",
              port: 22,
              username: "bioflow",
              auth_method: "ssh_config",
              ssh_alias: "bioflow-test-sz03",
              key_path: "",
              status: "online",
              skill_instructions: "Use /data/test.",
            },
          ],
        })
      }
      if (path === "/agent/skills") return Promise.resolve({ data: { skills: [] } })
      return Promise.resolve({ data: [] })
    })
    const runtime = {
      state: {
        session: baseSession,
        turns: [{ ...baseTurn, id: "running-turn", status: "running" }],
        events: [] as AgentRuntimeEvent[],
        timeline: buildAgentRuntimeTimeline(
          [{ ...baseTurn, id: "running-turn", status: "running" }],
          [],
        ),
        status: "running" as "idle" | "loading" | "running" | "error",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    }
    useAgentRuntimeMock.mockReturnValue(runtime)
    const view = render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Queued under auto" } })
    fireEvent.keyDown(input, { key: "Enter" })

    fireEvent.pointerDown(
      await screen.findByRole("button", {
        name: "Execution targets: Auto, All targets",
      }),
    )
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /Manual/ }))
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: /Test host sz03/ }),
    )

    runtime.state = {
      ...runtime.state,
      turns: [{ ...baseTurn, id: "running-turn", status: "completed" }],
      timeline: buildAgentRuntimeTimeline(
        [{ ...baseTurn, id: "running-turn", status: "completed" }],
        [],
      ),
      status: "idle",
    }
    view.rerender(<AgentWorkbench />)

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Queued under auto",
        expect.objectContaining({ executionScope: autoExecutionScope }),
      ),
    )
  })

  it("surfaces the latest runtime target in the selector pill", async () => {
    const runningTurn = { ...baseTurn, id: "running-turn", status: "running" as const }
    const remoteTargetEvent: AgentRuntimeEvent = {
      id: "risk-remote",
      session_id: "session-1",
      turn_id: runningTurn.id,
      seq: 1,
      type: "action.risk_assessed",
      payload: {
        action_id: "action-remote",
        target: {
          kind: "remote_ssh",
          trust_domain: "sz01.example.org",
          identity: "bioflow",
          connection_id: "connection-sz01",
        },
      },
      visibility: "user",
      schema_version: 1,
      created_at: "2026-07-13T00:00:00Z",
      updated_at: "2026-07-13T00:00:00Z",
    }
    const localTargetEvent: AgentRuntimeEvent = {
      ...remoteTargetEvent,
      id: "risk-local",
      seq: 2,
      payload: {
        action_id: "action-local",
        target: {
          kind: "local",
        },
      },
    }
    setupRuntime({
      session: {
        ...baseSession,
        execution_scope: autoExecutionScope,
      },
      turns: [runningTurn],
      events: [remoteTargetEvent],
      status: "running",
    })
    const view = render(<AgentWorkbench />)

    expect(
      await screen.findByRole("button", {
        name: "Execution targets: Auto, bioflow@sz01.example.org",
      }),
    ).toBeInTheDocument()

    setupRuntime({
      session: {
        ...baseSession,
        execution_scope: autoExecutionScope,
      },
      turns: [runningTurn],
      events: [remoteTargetEvent, localTargetEvent],
      status: "running",
    })
    view.rerender(<AgentWorkbench />)

    expect(
      await screen.findByRole("button", {
        name: "Execution targets: Auto, Local",
      }),
    ).toBeInTheDocument()
  })

  it("treats approval and user waits as active turns for queue policy", () => {
    writeAgentTurnPolicy("queue")
    const send = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: baseSession,
      turns: [{ ...baseTurn, id: "waiting-turn", status: "waiting_approval" }],
      send,
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "After approval" } })
    fireEvent.keyDown(input, { key: "Enter" })

    expect(send).not.toHaveBeenCalled()
    expect(screen.getByText("After approval")).toBeInTheDocument()
    expect(screen.getByText("Queued")).toBeInTheDocument()
  })

  it("hydrates the remote execution scope from session metadata before sending", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: {
        ...baseSession,
        metadata: { remote_connection_id: "11111111-1111-1111-1111-111111111111" },
      },
      send,
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the remote host" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Check the remote host",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope(
            "11111111-1111-1111-1111-111111111111",
          ),
        }),
      ),
    )
  })

  it("prefers a normalized session execution target over legacy remote metadata", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: {
        ...baseSession,
        execution_target: {
          kind: "remote_ssh",
          remote_connection_id: "normalized-connection",
        },
        metadata: { remote_connection_id: "legacy-connection" },
      } as AgentRuntimeSession,
      send,
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the normalized host" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Check the normalized host",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope("normalized-connection"),
        }),
      ),
    )
  })

  it("reads backend-normalized type and connection id execution targets", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: {
        ...baseSession,
        execution_target: {
          type: "remote_ssh",
          connection_id: "backend-normalized-connection",
        },
        metadata: { remote_connection_id: "legacy-connection" },
      } as AgentRuntimeSession,
      send,
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the backend host" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Check the backend host",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope("backend-normalized-connection"),
        }),
      ),
    )
  })

  it("sends the default auto execution scope before a session exists", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: null,
      send,
    })

    render(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the project host" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() => expect(send).toHaveBeenCalled())
    expect(send.mock.calls[0][1]).not.toHaveProperty("remoteConnectionId")
    expect(send.mock.calls[0][1]).toEqual(
      expect.objectContaining({ executionScope: autoExecutionScope }),
    )
  })

  it("keeps a draft manual remote selection when sending the first message", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") {
        return Promise.resolve({
          data: [
            {
              id: "connection-test-231",
              name: "Test host sz03",
              host: "10.227.5.231",
              port: 22,
              username: "bioflow",
              auth_method: "ssh_config",
              ssh_alias: "bioflow-test-sz03",
              key_path: "",
              status: "online",
              skill_instructions: "Use /data/test.",
            },
          ],
        })
      }
      return Promise.resolve({ data: [] })
    })
    setupRuntime({
      session: null,
      send,
    })

    render(<AgentWorkbench />)

    fireEvent.pointerDown(
      await screen.findByRole("button", {
        name: "Execution targets: Auto, All targets",
      }),
    )
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /Manual/ }))
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: /Test host sz03/ }),
    )
    fireEvent.click(await screen.findByRole("menuitemcheckbox", { name: /Local/ }))

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the remote host first" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Check the remote host first",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope("connection-test-231"),
        }),
      ),
    )
  })

  it("defaults a remote project draft conversation to the project connection", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    workspaceProjectsMock = [
      {
        id: "project-remote",
        name: "Simulation debug",
        storage_mode: "remote",
        remote_connection_id: "connection-test-231",
      },
    ]
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") {
        return Promise.resolve({
          data: [
            {
              id: "connection-test-231",
              name: "Test host sz03",
              host: "10.227.5.231",
              port: 22,
              username: "bioflow",
              auth_method: "ssh_config",
              ssh_alias: "bioflow-test-sz03",
              key_path: "",
              status: "online",
              skill_instructions: "Use /data/test.",
            },
          ],
        })
      }
      return Promise.resolve({ data: [] })
    })
    setupRuntime({
      session: null,
      send,
    })

    render(<AgentWorkbench projectId="project-remote" />)

    expect(
      await screen.findByRole("button", {
        name: "Execution targets: Manual, Test host sz03",
      }),
    ).toBeInTheDocument()

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Use this remote project" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Use this remote project",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope("connection-test-231"),
        }),
      ),
    )
  })

  it("sends a manual local execution scope when switching a remote session back to local", async () => {
    const send = vi.fn().mockResolvedValue(undefined)
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") {
        return Promise.resolve({
          data: [
            {
              id: "connection-test-231",
              name: "Test host sz03",
              host: "10.227.5.231",
              port: 22,
              username: "bioflow",
              auth_method: "ssh_config",
              ssh_alias: "bioflow-test-sz03",
              key_path: "",
              status: "online",
              skill_instructions: "Use /data/test.",
            },
          ],
        })
      }
      return Promise.resolve({ data: [] })
    })
    setupRuntime({
      session: {
        ...baseSession,
        metadata: { remote_connection_id: "connection-test-231" },
      },
      send,
    })

    render(<AgentWorkbench />)

    fireEvent.pointerDown(
      await screen.findByRole("button", {
        name: "Execution targets: Manual, Test host sz03",
      }),
    )
    fireEvent.click(
      await screen.findByRole("menuitemcheckbox", { name: /Test host sz03/ }),
    )

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Run locally now" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Run locally now",
        expect.objectContaining({ executionScope: manualLocalExecutionScope }),
      ),
    )
  })

  it("resyncs the remote connection selection when the active session changes", async () => {
    const firstSend = vi.fn().mockResolvedValue(undefined)
    const secondSend = vi.fn().mockResolvedValue(undefined)
    setupRuntime({
      session: {
        ...baseSession,
        id: "session-1",
        metadata: { remote_connection_id: "connection-test-231" },
      },
      send: firstSend,
    })
    const { rerender } = render(<AgentWorkbench />)

    setupRuntime({
      session: {
        ...baseSession,
        id: "session-2",
        metadata: { remote_connection_id: "connection-uat-245" },
      },
      send: secondSend,
    })
    rerender(<AgentWorkbench />)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Check the new host" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(secondSend).toHaveBeenCalledWith(
        "Check the new host",
        expect.objectContaining({
          executionScope: manualRemoteExecutionScope("connection-uat-245"),
        }),
      ),
    )
    expect(firstSend).not.toHaveBeenCalled()
  })

  it("opens a placeholder attachment menu without sending a message", async () => {
    const send = vi.fn()
    useAgentRuntimeMock.mockReturnValue({
      state: {
        session: null,
        turns: [],
        events: [],
        timeline: [],
        status: "idle",
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send,
      interrupt: vi.fn(),
      decideAction: vi.fn(),
    })

    render(<AgentWorkbench />)

    fireEvent.pointerDown(
      screen.getByRole("button", { name: "Attach or add context" }),
    )

    expect(
      await screen.findByRole("menuitem", { name: "Attach files" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Browse project files" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Reference a run" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Run preflight" }),
    ).toBeInTheDocument()
    expect(
      screen.getByRole("menuitem", { name: "Diagnose run" }),
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole("menuitem", { name: "Attach files" }))

    expect(send).not.toHaveBeenCalled()
  })

  it("renders a compact composer jump prompt and inline approval controls", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [waitingDecisionEvent],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.getByTestId("composer-approval-popover")).toBeInTheDocument()
    expect(screen.getByTestId("composer-decision-jump")).toBeInTheDocument()
    expect(
      within(screen.getByTestId("composer-approval-popover")).getByText(
        "Needs confirmation · Jump",
      ),
    ).toBeInTheDocument()
    expect(screen.getByTestId("inline-approval-card")).toBeInTheDocument()
    expect(screen.queryByTestId("pending-decisions")).not.toBeInTheDocument()
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
    expect(screen.getByText("Needs your decision")).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Approve" })).toHaveLength(1)
    expect(screen.getAllByRole("button", { name: "Reject" })).toHaveLength(1)
  })

  it("hands inline approval focus to the next request and announces it", async () => {
    const waitingTurn: AgentRuntimeTurn = {
      ...baseTurn,
      status: "waiting_approval",
      final_text: null,
    }
    const runtime = {
      state: {
        session: baseSession,
        turns: [waitingTurn],
        events: [
          waitingDecisionEvent,
          {
            ...waitingDecisionEvent,
            id: "event-2",
            seq: 2,
            payload: { action_id: "action-2", name: "remote.exec" },
          },
        ],
        timeline: buildAgentRuntimeTimeline(
          [waitingTurn],
          [
            waitingDecisionEvent,
            {
              ...waitingDecisionEvent,
              id: "event-2",
              seq: 2,
              payload: { action_id: "action-2", name: "remote.exec" },
            },
          ],
        ),
        status: "running" as const,
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send: vi.fn(),
      interrupt: vi.fn(),
      decideAction: vi.fn(async (actionId: string) => {
        runtime.state.events = runtime.state.events.filter(
          (event) => event.payload.action_id !== actionId,
        )
        runtime.state.timeline = buildAgentRuntimeTimeline(
          runtime.state.turns,
          runtime.state.events,
        )
        view.rerender(<AgentWorkbench />)
      }),
      permissionMode: "guarded_auto" as const,
      setPermissionMode: vi.fn(),
      permissionUpdate: {
        status: "idle" as const,
        mode: null,
        pendingStrategy: null,
        reconciliation: null,
        error: null,
      },
      retryPermissionModeUpdate: vi.fn(),
    }
    useAgentRuntimeMock.mockImplementation(() => runtime)
    const view = render(<AgentWorkbench />)

    const cards = screen.getAllByTestId("inline-approval-card")
    fireEvent.click(within(cards[0]).getByRole("button", { name: "Approve" }))

    await waitFor(() =>
      expect(screen.getByTestId("inline-approval-card")).toHaveFocus(),
    )
    expect(screen.getByRole("status")).toHaveTextContent(
      "Decision submitted. Moved to the next request.",
    )
  })

  it("returns inline approval focus to the composer after the last request", async () => {
    const waitingTurn: AgentRuntimeTurn = {
      ...baseTurn,
      status: "waiting_approval",
      final_text: null,
    }
    const runtime = {
      state: {
        session: baseSession,
        turns: [waitingTurn],
        events: [waitingDecisionEvent],
        timeline: buildAgentRuntimeTimeline(
          [waitingTurn],
          [waitingDecisionEvent],
        ),
        status: "running" as const,
        error: null,
      },
      setActiveSessionId: vi.fn(),
      send: vi.fn(),
      interrupt: vi.fn(),
      decideAction: vi.fn(async () => {
        runtime.state.events = []
        runtime.state.timeline = buildAgentRuntimeTimeline(
          runtime.state.turns,
          runtime.state.events,
        )
        view.rerender(<AgentWorkbench />)
      }),
      permissionMode: "guarded_auto" as const,
      setPermissionMode: vi.fn(),
      permissionUpdate: {
        status: "idle" as const,
        mode: null,
        pendingStrategy: null,
        reconciliation: null,
        error: null,
      },
      retryPermissionModeUpdate: vi.fn(),
    }
    useAgentRuntimeMock.mockImplementation(() => runtime)
    const view = render(<AgentWorkbench />)

    fireEvent.click(screen.getByRole("button", { name: "Approve" }))

    await waitFor(() =>
      expect(screen.getByPlaceholderText("Message Bioinfoflow...")).toHaveFocus(),
    )
    expect(screen.getByRole("status")).toHaveTextContent(
      "Decision submitted. Focus returned to the composer.",
    )
  })

  it("defaults widening permission changes to future operations and excludes interactions", async () => {
    const setPermissionMode = vi.fn().mockResolvedValue(null)
    const questionEvent: AgentRuntimeEvent = {
      ...waitingDecisionEvent,
      id: "event-question",
      seq: 3,
      payload: {
        action_id: "action-question",
        name: "ask_user",
        interaction: {
          kind: "user_input",
          questions: [
            {
              header: "Scope",
              question: "Which scope?",
              options: [{ label: "Current" }],
            },
          ],
        },
      },
    }
    setupRuntime({
      session: baseSession,
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          payload: { action_id: "action-2", name: "remote.exec" },
        },
        questionEvent,
      ],
      status: "running",
      permissionMode: "guarded_auto",
      setPermissionMode,
    })

    render(<AgentWorkbench />)
    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /Full access/ }))

    const dialog = await screen.findByRole("dialog", { name: "Update permission mode?" })
    expect(within(dialog).getByText(/2 waiting tool operations can be approved/)).toBeInTheDocument()
    expect(within(dialog).getByText(/1 interactions stay pending/)).toBeInTheDocument()
    fireEvent.click(
      within(dialog).getByRole("button", { name: "Only update future operations" }),
    )

    expect(setPermissionMode).toHaveBeenCalledWith("bypass", "future_only")
  })

  it("can widen permissions and approve only the current waiting tools", async () => {
    const setPermissionMode = vi.fn().mockResolvedValue(null)
    setupRuntime({
      session: baseSession,
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          payload: { action_id: "action-2", name: "remote.exec" },
        },
      ],
      status: "running",
      permissionMode: "guarded_auto",
      setPermissionMode,
    })

    render(<AgentWorkbench />)
    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    fireEvent.click(await screen.findByRole("menuitemradio", { name: /Full access/ }))
    const dialog = await screen.findByRole("dialog", { name: "Update permission mode?" })
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "Update and approve 2 waiting tools",
      }),
    )

    expect(setPermissionMode).toHaveBeenCalledWith(
      "bypass",
      "approve_pending_tools",
    )
  })

  it("applies permission tightening directly even when tools are waiting", async () => {
    const setPermissionMode = vi.fn().mockResolvedValue(null)
    setupRuntime({
      session: { ...baseSession, permission_mode: "bypass" },
      turns: [{ ...baseTurn, status: "waiting_approval", final_text: null }],
      events: [waitingDecisionEvent],
      status: "running",
      permissionMode: "bypass",
      setPermissionMode,
    })

    render(<AgentWorkbench />)
    fireEvent.pointerDown(screen.getByRole("button", { name: "Permission mode" }))
    fireEvent.click(
      await screen.findByRole("menuitemradio", { name: /Approve for me/ }),
    )

    expect(screen.queryByRole("dialog", { name: "Update permission mode?" })).not.toBeInTheDocument()
    expect(setPermissionMode).toHaveBeenCalledWith("guarded_auto", "future_only")
  })

  it("keeps the default workspace panel stable while the agent is streaming", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        {
          ...waitingDecisionEvent,
          type: "assistant.text.delta",
          payload: { content: "thinking" },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
  })

  it("renders thinking and tool-call activity in the transcript", async () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        {
          id: "event-thinking",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 1,
          type: "assistant.thinking.completed",
          payload: {
            message_id: "message-1",
            content: "Inspecting the project state.",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
        {
          id: "event-tool",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 2,
          type: "assistant.tool_call.completed",
          payload: {
            message_id: "message-1",
            call_id: "call-1",
            name: "projects__list",
            arguments: { limit: 1 },
            status: "completed",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
        {
          id: "event-text",
          session_id: "session-1",
          turn_id: "turn-1",
          seq: 3,
          type: "assistant.text.completed",
          payload: {
            message_id: "message-1",
            text: "Project scan complete.",
            content: "Project scan complete.",
            index: 0,
          },
          visibility: "user",
          schema_version: 1,
          created_at: "2026-06-09T00:00:00Z",
          updated_at: "2026-06-09T00:00:00Z",
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(await screen.findByText("Thinking")).toBeInTheDocument()
    expect(screen.getByText("Project scan complete.")).toBeInTheDocument()
    expect(screen.getByText("Read 1 source")).toBeInTheDocument()
  })

  it("keeps an approved approval visible in the transcript until resume progress arrives", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          type: "action.decision_recorded",
          payload: { action_id: "action-1", decision: "approve" },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.queryByTestId("composer-approval-popover")).not.toBeInTheDocument()
    expect(screen.getAllByText("Approved, resuming").length).toBeGreaterThan(0)
    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()
  })

  it("clears the approved approval once resume progress arrives", () => {
    setupRuntime({
      turns: [{ ...baseTurn, status: "running", final_text: null }],
      events: [
        waitingDecisionEvent,
        {
          ...waitingDecisionEvent,
          id: "event-2",
          seq: 2,
          type: "action.decision_recorded",
          payload: { action_id: "action-1", decision: "approve" },
        },
        {
          ...waitingDecisionEvent,
          id: "event-3",
          seq: 3,
          type: "assistant.text.delta",
          payload: { content: "Resumed." },
        },
      ],
      status: "running",
    })

    render(<AgentWorkbench />)

    expect(screen.queryByTestId("composer-approval-popover")).not.toBeInTheDocument()
    expect(screen.getByText("Approved, resuming")).toBeInTheDocument()
  })

  it("does not dock an older turn todo over a newer turn", async () => {
    apiRequestMock.mockImplementation((path: string) =>
      path === "/connections" ? new Promise(() => {}) : Promise.resolve({ data: [priorTodoArtifact] }),
    )
    setupRuntime({
      session: baseSession,
      turns: [
        baseTurn,
        {
          ...baseTurn,
          id: "turn-2",
          input_text: "Now inspect the report.",
          final_text: "The report is ready.",
          created_at: "2026-06-09T00:01:00Z",
          updated_at: "2026-06-09T00:01:00Z",
        },
      ],
    })

    render(<AgentWorkbench />)

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/artifacts")
    })
    expect(screen.queryByTestId("agent-todo-dock")).not.toBeInTheDocument()
    expect(screen.queryByText("Working old task")).not.toBeInTheDocument()
  })
})
