import type * as React from "react"
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentWorkbench } from "@/components/bioinfoflow/agent-runtime/agent-workbench"
import type {
  AgentRuntimeArtifact,
  AgentRuntimeEvent,
  AgentRuntimeSession,
  AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"

const useAgentRuntimeMock = vi.fn()
const useLlmSettingsMock = vi.fn()
const useIsMobileMock = vi.fn(() => false)
const setNavbarActionsMock = vi.fn()
const apiRequestMock = vi.fn()

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      welcomeTitle: "What should Bioinfoflow help you do today?",
      composerPlaceholder: "Message Bioinfoflow...",
      attach: "Attach or add context",
      send: "Send message",
      stop: "Stop response",
      pendingResponse: "Working on it...",
      thinking: "Thinking",
      showThinking: "Show thinking",
      hideThinking: "Hide thinking",
      toolCalls: "Tool calls",
      "activity.groups.read": "Read data",
      "activity.summary.read": "Read 1 source",
      approve: "Approve",
      reject: "Reject",
      "approval.state.approved": "Approved, resuming",
      "approval.jumpToDecision": "Needs confirmation · Jump",
      "turnStatus.running": "Working",
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
      "tabs.files": "Files",
      "tabs.browser": "Browser",
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
      menuTitle: "Local / Remote",
      manage: "Manage SSH hosts",
      "local.label": "Local",
      "local.description": "Run in this Bioinfoflow workspace",
      "remote.label": "Remote",
      emptyRemoteHosts: "No remote hosts configured.",
      loadFailed: "Could not load remote hosts.",
      "status.online": "Online",
      "status.offline": "Offline",
      "status.error": "Connection error",
      "status.unknown": "Not tested",
      selectedLocalAria: "Current execution target: local",
      selectedRemoteAria: `Current execution target: ${values?.name ?? ""} at ${values?.host ?? ""}, ${values?.status ?? ""}`,
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
}: {
  session?: AgentRuntimeSession | null
  turns?: AgentRuntimeTurn[]
  events?: AgentRuntimeEvent[]
  status?: "idle" | "loading" | "running" | "error"
  send?: ReturnType<typeof vi.fn>
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
  })
}

describe("AgentWorkbench", () => {
  beforeEach(() => {
    useAgentRuntimeMock.mockReset()
    useLlmSettingsMock.mockReset()
    useIsMobileMock.mockReset()
    useIsMobileMock.mockReturnValue(false)
    setNavbarActionsMock.mockReset()
    apiRequestMock.mockReset()
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/connections") return new Promise(() => {})
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

  it("registers the runtime sidecar toggle with the navbar action group", () => {
    render(<AgentWorkbench />)

    expect(setNavbarActionsMock).toHaveBeenCalled()
    const lastCall = setNavbarActionsMock.mock.calls.at(-1)
    expect(lastCall?.[0]).toBeTruthy()
    expect(
      screen.queryByRole("button", { name: "Open workspace panel" }),
    ).not.toBeInTheDocument()
  })

  it("opens the desktop workspace drawer to project files on first user request", async () => {
    setupRuntime({ session: baseSession })
    render(<AgentWorkbench projectId="project-1" />)
    const navbarActions = setNavbarActionsMock.mock.calls.at(-1)?.[0] as React.ReactElement
    render(<>{navbarActions}</>)

    expect(screen.queryByTestId("artifact-panel")).not.toBeInTheDocument()

    await act(async () => {
      fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
      await Promise.resolve()
    })

    const drawer = screen.getByTestId("artifact-panel")
    expect(drawer).toBeInTheDocument()
    expect(within(drawer).getByRole("button", { name: "Files" })).toHaveAttribute(
      "data-active",
      "true",
    )
    expect(within(drawer).queryByRole("button", { name: "Tools" })).not.toBeInTheDocument()
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

    fireEvent.click(screen.getByRole("button", { name: "Browser" }))
    const input = screen.getByPlaceholderText("browser.urlPlaceholder")
    fireEvent.change(input, { target: { value: "/runs" } })
    fireEvent.click(screen.getByRole("button", { name: "browser.go" }))
    expect(screen.getByTitle("browser.title")).toHaveAttribute(
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

    expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute(
      "data-active",
      "true",
    )
    fireEvent.click(screen.getByRole("button", { name: "Browser" }))
    expect(screen.getByPlaceholderText("browser.urlPlaceholder")).toHaveValue("")
    expect(screen.getByText("Enter a URL to preview a page.")).toBeInTheDocument()
    expect(screen.queryByTitle("browser.title")).not.toBeInTheDocument()
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

    fireEvent.click(screen.getByRole("button", { name: "Browser" }))
    expect(screen.getByRole("button", { name: "Browser" })).toHaveAttribute(
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

    expect(screen.getByRole("button", { name: "Browser" })).toHaveAttribute(
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

    fireEvent.click(screen.getByRole("button", { name: "Browser" }))
    const input = screen.getByPlaceholderText("browser.urlPlaceholder")
    fireEvent.change(input, { target: { value: "/runs" } })
    fireEvent.click(screen.getByRole("button", { name: "browser.go" }))
    expect(screen.getByTitle("browser.title")).toHaveAttribute(
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

    expect(screen.getByPlaceholderText("browser.urlPlaceholder")).toHaveValue(
      "http://localhost:3000/runs",
    )
    expect(screen.getByTitle("browser.title")).toHaveAttribute(
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
    const mobilePanel = screen.getByTestId("artifact-panel")
    expect(mobilePanel).toBeInTheDocument()
    expect(mobilePanel).toHaveClass("flex")
    expect(mobilePanel).not.toHaveClass("hidden")
    expect(screen.getByRole("button", { name: "Files" })).toHaveAttribute(
      "data-active",
      "true",
    )
    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/artifacts")
    })
  })

  it("moves the composer to the bottom after a turn exists", () => {
    setupRuntime({ turns: [baseTurn] })

    render(<AgentWorkbench />)

    expect(screen.getByText("Analyze these FASTQ files.")).toBeInTheDocument()
    expect(screen.getByText("The files look ready.")).toBeInTheDocument()
    expect(screen.getByTestId("agent-composer-shell")).toHaveAttribute(
      "data-placement",
      "bottom",
    )
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

  it("hydrates the remote connection selection from session metadata before sending", async () => {
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
          remoteConnectionId: "11111111-1111-1111-1111-111111111111",
        }),
      ),
    )
  })

  it("does not send a null remote connection override before a session exists", async () => {
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
  })

  it("sends an empty remote connection override when switching a remote session back to local", async () => {
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
        name: "Current execution target: Test host sz03 at 10.227.5.231, Online",
      }),
    )
    fireEvent.click(screen.getAllByText("Local").at(-1)!)

    const input = screen.getByPlaceholderText("Message Bioinfoflow...")
    fireEvent.change(input, { target: { value: "Run locally now" } })
    fireEvent.keyDown(input, { key: "Enter" })

    await waitFor(() =>
      expect(send).toHaveBeenCalledWith(
        "Run locally now",
        expect.objectContaining({ remoteConnectionId: "" }),
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
        expect.objectContaining({ remoteConnectionId: "connection-uat-245" }),
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
