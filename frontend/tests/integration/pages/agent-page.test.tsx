import * as React from "react"
import { act, fireEvent, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import AgentPage from "@/app/(app)/agent/page"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
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
  })

  it("keeps the right sidebar hidden by default and toggles with the keyboard shortcut", async () => {
    localStorage.setItem("right-sidebar-width", "512")
    localStorage.setItem("right-sidebar-collapsed", "false")

    useEventsMock.mockReturnValue({ connectionState: "connected" })

    renderAppPage(<AgentPage />, {
      projectContext: { activeProjectId: "project-1" },
    })

    expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:project-1|workspace:on")
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

    expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:none|workspace:off")
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("select project"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:project-9|workspace:on")
    })
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()

    fireEvent.click(screen.getByText("clear project"))

    await waitFor(() => {
      expect(screen.getByTestId("chat-stream")).toHaveTextContent("chat:none|workspace:off")
    })
    expect(screen.queryByText("toggle live deck")).not.toBeInTheDocument()
  })
})
