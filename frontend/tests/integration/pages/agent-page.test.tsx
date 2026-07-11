import * as React from "react"
import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import AgentSessionPage from "@/app/(app)/agent/[sessionId]/page"
import AgentPage, { AgentPageContent } from "@/app/(app)/agent/page"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { renderAppPage } from "@/tests/app-test-utils"

// Per-test mock state, scoped to this file and reset before each test
let mockRunToSelect: Record<string, unknown> | null = null

const useEventsMock = vi.fn()
const useIsMobileMock = vi.fn(() => false)
const useParamsMock = vi.fn(() => ({ sessionId: "session-9" }))
const workspaceShellMock = vi.fn(() => undefined)
const getAgentRuntimeSessionMock = vi.fn()
const apiRequestMock = vi.fn()

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => useEventsMock(...args),
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => useIsMobileMock(),
}))

vi.mock("next/navigation", () => ({
  useParams: () => useParamsMock(),
}))

vi.mock("@/lib/agent-runtime/client", () => ({
  getAgentRuntimeSession: (...args: unknown[]) =>
    getAgentRuntimeSessionMock(...args),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: (...args: unknown[]) => apiRequestMock(...args),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useOptionalWorkspaceShell: () => workspaceShellMock(),
}))

vi.mock("@/components/bioinfoflow/agent-runtime/agent-workbench", () => ({
  AgentWorkbench: ({
    projectId,
    activeSessionId,
    workspaceEnabled,
    className,
  }: {
    projectId?: string
    activeSessionId?: string
    workspaceEnabled?: boolean
    className?: string
  }) => (
    <div data-testid="agent-workbench" className={className}>
      agent-workbench:{projectId || "none"}|session:{activeSessionId || "draft"}|workspace:{workspaceEnabled ? "on" : "off"}
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/live-deck", () => ({
  LiveDeck: ({
    activeTab,
    runId,
    dag,
    onCollapse,
    onRunSelect,
  }: {
    activeTab: string
    runId?: string
    dag?: { nodes?: unknown[] } | null
    onCollapse: () => void
    onRunSelect: (run: Record<string, unknown> | null) => void
  }) => (
    <div data-testid="live-deck">
      <div>tab:{activeTab}</div>
      <div>run:{runId || "none"}</div>
      <div>dag:{dag ? "present" : "missing"}</div>
      <button onClick={() => onRunSelect(mockRunToSelect)}>select run</button>
      <button onClick={onCollapse}>collapse live deck</button>
    </div>
  ),
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: () => <div data-testid="resize-handle" />,
}))

vi.mock("@/components/ui/sidebar-toggle", () => ({
  SidebarToggle: ({ onToggle }: { onToggle: () => void }) => (
    <button onClick={onToggle}>toggle live deck</button>
  ),
}))

function ProjectSelectionHarness() {
  const { setActiveProjectId } = useProjectContext()

  return (
    <>
      <button onClick={() => setActiveProjectId("project-9")}>select project</button>
      <button onClick={() => setActiveProjectId("")}>clear project</button>
    </>
  )
}

describe("AgentPage", () => {
  beforeEach(() => {
    mockRunToSelect = null
    localStorage.clear()
    workspaceShellMock.mockReset()
    workspaceShellMock.mockReturnValue(undefined)
    useParamsMock.mockReset()
    useParamsMock.mockReturnValue({ sessionId: "session-9" })
    getAgentRuntimeSessionMock.mockReset()
    getAgentRuntimeSessionMock.mockResolvedValue({
      id: "session-9",
      project_id: "project-2",
      workspace_id: "workspace-1",
      user_id: "dev",
      role_profile: "bioinformatician",
      permission_mode: "guarded_auto",
      automation_mode: "assisted",
      runtime_mode: "api",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z",
    })
    apiRequestMock.mockReset()
    apiRequestMock.mockResolvedValue({
      data: { id: "project-default", name: "Inbox", is_default: true },
    })
  })

  it("keeps the right sidebar hidden by default and toggles with the keyboard shortcut", async () => {
    localStorage.setItem("right-sidebar-width", "512")
    localStorage.setItem("right-sidebar-collapsed", "false")

    useEventsMock.mockReturnValue({ connectionState: "connected" })

    renderAppPage(<AgentPage />, {
      projectContext: { activeProjectId: "project-1" },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:project-1|session:draft|workspace:on")
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })

    expect(await screen.findByTestId("live-deck")).toHaveTextContent("tab:workspace")
    expect(screen.getByTestId("live-deck").parentElement?.className).toContain("animate-in")
    expect(screen.getByTestId("live-deck").parentElement?.className).toContain("slide-in-from-right-2")

    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })

    await waitFor(() => {
      expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    })

    expect(localStorage.getItem("right-sidebar-collapsed")).toBe("true")
  })

  it("updates DAG state without auto-opening the hidden live deck", async () => {
    let onRunDag: ((event: { data: { run_id: string; dag: { nodes: unknown[] } } }) => void) | undefined
    useEventsMock.mockImplementation((options: { onRunDag?: typeof onRunDag }) => {
      onRunDag = options.onRunDag
      return { connectionState: "connected" }
    })

    localStorage.setItem("right-sidebar-collapsed", "false")

    mockRunToSelect = {
      run_id: "run-123",
      id: "run-model-id",
      project_id: "project-2",
      workflow_id: null,
      status: "running",
      workspace: ".",
      config: {},
      samples_count: 0,
      tasks_total: 0,
      tasks_completed: 0,
    }

    renderAppPage(<AgentPage />, {
      projectContext: { activeProjectId: "project-2" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })

    expect(await screen.findByTestId("live-deck")).toHaveTextContent("dag:missing")

    fireEvent.click(screen.getByText("select run"))
    fireEvent.click(screen.getByText("collapse live deck"))

    await waitFor(() => {
      expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    })

    act(() => {
      onRunDag?.({ data: { run_id: "run-other", dag: { nodes: [{ id: "n1" }] } } })
    })
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()

    act(() => {
      onRunDag?.({ data: { run_id: "run-123", dag: { nodes: [{ id: "n1" }] } } })
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()

    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })

    expect(await screen.findByTestId("live-deck")).toHaveTextContent("tab:dag")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("dag:present")
  })

  it("keeps inbox conversations off the live deck while allowing draft chat", () => {
    renderAppPage(<AgentPage />, {
      projectContext: {
        selectedProjectId: "",
        conversationProjectId: "project-default",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:project-default|session:draft|workspace:on")
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
  })

  it("uses min-width-safe shell classes so the composer survives right-side panels", () => {
    renderAppPage(
      <AgentPageContent
        selectedProjectId="project-1"
        conversationProjectId="project-1"
        activeConversationId=""
      />,
    )

    expect(screen.getByTestId("agent-page-shell").className).toContain("min-w-0")
    expect(screen.getByTestId("agent-page-shell").className).toContain("min-h-0")
    expect(screen.getByTestId("agent-page-shell").className).toContain("overflow-hidden")
    expect(screen.getByTestId("agent-workbench").className).toContain("min-w-0")
    expect(screen.getByTestId("agent-workbench").className).toContain("flex-1")
  })

  it("moves from project selection into workspace mode and back out without leaking the live deck state", async () => {
    renderAppPage(
      <>
        <ProjectSelectionHarness />
        <AgentPage />
      </>,
      {
        projectContext: {
          selectedProjectId: "",
          conversationProjectId: "",
          activeProjectId: "",
        },
      },
    )

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:none|session:draft|workspace:on")
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("select project"))

    await waitFor(() => {
      expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:project-9|session:draft|workspace:on")
    })
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("clear project"))

    await waitFor(() => {
      expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:none|session:draft|workspace:on")
    })
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()
  })

  it("passes a route-selected session id into the shared agent page content", () => {
    renderAppPage(
      <AgentPageContent
        selectedProjectId="project-1"
        conversationProjectId="project-1"
        activeConversationId="session-9"
      />,
    )

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
      "agent-workbench:project-1|session:session-9|workspace:on",
    )
  })

  it("loads a deep-linked session and syncs its owning project into page context", async () => {
    renderAppPage(<AgentSessionPage />, {
      projectContext: {
        selectedProjectId: "project-stale",
        conversationProjectId: "project-stale",
      },
    })

    expect(getAgentRuntimeSessionMock).toHaveBeenCalledWith("session-9")

    await waitFor(() => {
      expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
        "agent-workbench:project-2|session:session-9|workspace:on",
      )
    })
    expect(localStorage.getItem("bioinfoflow:agent-core-session:project-2")).toBe(
      "session-9",
    )
  })

  it("keeps default-project deep links in inbox mode", async () => {
    localStorage.setItem("right-sidebar-collapsed", "false")
    getAgentRuntimeSessionMock.mockResolvedValue({
      id: "session-inbox",
      project_id: "project-default",
      workspace_id: "workspace-1",
      user_id: "dev",
      role_profile: "bioinformatician",
      permission_mode: "guarded_auto",
      automation_mode: "assisted",
      runtime_mode: "api",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z",
    })
    useParamsMock.mockReturnValue({ sessionId: "session-inbox" })

    renderAppPage(<AgentSessionPage />, {
      projectContext: {
        selectedProjectId: "project-stale",
        conversationProjectId: "project-stale",
      },
    })

    await waitFor(() => {
      expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
        "agent-workbench:project-default|session:session-inbox|workspace:on",
      )
    })
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()
  })

  it("does not mount the deep-linked workbench before route session reconciliation", async () => {
    let resolveSession: (value: Awaited<ReturnType<typeof getAgentRuntimeSessionMock>>) => void
    getAgentRuntimeSessionMock.mockReturnValue(
      new Promise((resolve) => {
        resolveSession = resolve
      }),
    )

    renderAppPage(<AgentSessionPage />, {
      projectContext: {
        selectedProjectId: "project-stale",
        conversationProjectId: "project-stale",
      },
    })

    expect(screen.queryByTestId("agent-workbench")).not.toBeInTheDocument()

    resolveSession!({
      id: "session-9",
      project_id: "project-2",
      workspace_id: "workspace-1",
      user_id: "dev",
      role_profile: "bioinformatician",
      permission_mode: "guarded_auto",
      automation_mode: "assisted",
      runtime_mode: "api",
      status: "active",
      created_at: "2026-06-08T00:00:00Z",
      updated_at: "2026-06-08T00:00:00Z",
    })

    await waitFor(() => {
      expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
        "agent-workbench:project-2|session:session-9|workspace:on",
      )
    })
  })

  it("leaves project restoration to the workspace shell instead of restoring inside AgentPage", async () => {
    localStorage.setItem("bioinfoflow:last-used-project", "project-9")
    workspaceShellMock.mockReturnValue({
      projects: [
        { id: "project-1", name: "Alpha" },
        { id: "project-9", name: "Omega" },
      ],
      defaultProject: { id: "project-default", name: "Recent", is_default: true },
    })

    renderAppPage(<AgentPage />, {
      projectContext: {
        selectedProjectId: "",
        conversationProjectId: "",
        activeProjectId: "",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent("agent-workbench:none|session:draft|workspace:on")
  })
})
