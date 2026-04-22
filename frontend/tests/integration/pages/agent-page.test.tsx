import { fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import AgentPage from "@/app/(app)/agent/page"
import { renderAppPage } from "@/tests/app-test-utils"

// Per-test mock state, scoped to this file and reset before each test
let mockRunToSelect: Record<string, unknown> | null = null

const useEventsMock = vi.fn()
const useIsMobileMock = vi.fn(() => false)

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => useEventsMock(...args),
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => useIsMobileMock(),
}))

vi.mock("@/components/bioinfoflow/chat-stream", () => ({
  ChatStream: ({
    projectId,
    workspaceEnabled,
  }: {
    projectId?: string
    workspaceEnabled?: boolean
  }) => (
    <div data-testid="chat-stream">
      chat:{projectId || "none"}|workspace:{workspaceEnabled ? "on" : "off"}
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

describe("AgentPage", () => {
  beforeEach(() => {
    mockRunToSelect = null
  })

  it("restores persisted sidebar state and toggles with the keyboard shortcut", async () => {
    localStorage.setItem("right-sidebar-width", "512")
    localStorage.setItem("right-sidebar-collapsed", "false")

    useEventsMock.mockReturnValue({ connectionState: "connected" })

    renderAppPage(<AgentPage />, {
      projectContext: { activeProjectId: "project-1" },
    })

    expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:project-1|workspace:on")
    expect(await screen.findByTestId("live-deck")).toHaveTextContent("tab:workspace")
    expect(screen.getByTestId("live-deck").parentElement?.className).toContain("animate-in")
    expect(screen.getByTestId("live-deck").parentElement?.className).toContain("slide-in-from-right-2")

    fireEvent.keyDown(window, { key: "b", ctrlKey: true, shiftKey: true })

    await waitFor(() => {
      expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    })

    expect(localStorage.getItem("right-sidebar-collapsed")).toBe("true")
  })

  it("opens the live deck on DAG events for the selected run only", async () => {
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

    expect(await screen.findByTestId("live-deck")).toHaveTextContent("dag:missing")

    fireEvent.click(screen.getByText("select run"))
    fireEvent.click(screen.getByText("collapse live deck"))

    await waitFor(() => {
      expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    })

    onRunDag?.({ data: { run_id: "run-other", dag: { nodes: [{ id: "n1" }] } } })
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()

    onRunDag?.({ data: { run_id: "run-123", dag: { nodes: [{ id: "n1" }] } } })

    await waitFor(() => {
      expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:dag")
      expect(screen.getByTestId("live-deck")).toHaveTextContent("dag:present")
    })
  })

  it("keeps inbox conversations chat-only without selecting a real project", () => {
    renderAppPage(<AgentPage />, {
      projectContext: {
        selectedProjectId: "",
        conversationProjectId: "project-default",
      },
    })

    expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:project-default|workspace:off")
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
  })
})
