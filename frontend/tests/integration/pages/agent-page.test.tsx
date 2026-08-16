import { forwardRef, useImperativeHandle, type ReactNode } from "react"
import { fireEvent, render, screen } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AgentSessionPage from "@/app/(app)/agent/[sessionId]/page"
import AgentPage from "@/app/(app)/agent/page"
import { renderAppPage } from "@/tests/app-test-utils"

const mocks = vi.hoisted(() => ({
  params: vi.fn(() => ({ sessionId: "session-9" })),
  useEvents: vi.fn(),
  isMobile: vi.fn(() => false),
  workbench: vi.fn(),
  setNavbarActions: vi.fn(),
}))

vi.mock("next/navigation", () => ({
  useParams: () => mocks.params(),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
  usePathname: () => "/agent",
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    ({
      "workspacePanel.open": "Open workspace panel",
      "workspacePanel.close": "Close workspace panel",
      "workspacePanel.action": "Workspace",
      "workspacePanel.title": "Workspace panel",
      "workspacePanel.description": "Workspace details",
    })[key] ?? key,
}))

vi.mock("@/hooks/use-events", () => ({
  useEvents: (...args: unknown[]) => mocks.useEvents(...args),
}))

vi.mock("@/hooks/use-media-query", () => ({
  useIsMobile: () => mocks.isMobile(),
}))

vi.mock("@/components/bioinfoflow/workspace-shell-context", () => ({
  useWorkspaceShell: () => ({
    setNavbarActions: mocks.setNavbarActions,
  }),
}))

vi.mock("@/components/bioinfoflow/agent/agent-workbench", () => ({
  AgentWorkbench: forwardRef(function MockAgentWorkbench(
    props: {
      sessionId: string | null
      projectId: string | null
      onSessionResolved?: (session: unknown) => void
      headerActions?: ReactNode
      onOpenRun?: (runId: string) => void
    },
    ref,
  ) {
    mocks.workbench(props)
    useImperativeHandle(ref, () => ({
      focusInput: vi.fn(),
      stop: vi.fn(),
      newConversation: vi.fn(),
    }))
    return (
      <div data-testid="agent-workbench">
        session:{props.sessionId ?? "draft"}|project:{props.projectId ?? "none"}
        {props.headerActions}
        <button type="button" onClick={() => props.onOpenRun?.("run-42")}>
          Open referenced run
        </button>
      </div>
    )
  }),
}))

vi.mock("@/components/bioinfoflow/live-deck", () => ({
  LiveDeck: ({
    onCollapse,
    activeTab,
    runId,
  }: {
    onCollapse: () => void
    activeTab: string
    runId?: string | null
  }) => (
    <div data-testid="live-deck">
      tab:{activeTab}|run:{runId ?? "none"}
      <button type="button" onClick={onCollapse}>close</button>
    </div>
  ),
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: () => <div data-testid="resize-handle" />,
}))

describe("Agent pages", () => {
  beforeEach(() => {
    localStorage.clear()
    mocks.params.mockReturnValue({ sessionId: "session-9" })
    mocks.useEvents.mockReset()
    mocks.workbench.mockReset()
    mocks.setNavbarActions.mockReset()
    mocks.isMobile.mockReturnValue(false)
  })

  it("treats /agent as a new draft even when app context still names an old session", () => {
    renderAppPage(<AgentPage />, {
      projectContext: {
        activeConversationId: "session-old",
        selectedProjectId: "project-1",
        conversationProjectId: "project-1",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
      "session:draft|project:project-1",
    )
    expect(mocks.workbench).toHaveBeenLastCalledWith(
      expect.objectContaining({ sessionId: null }),
    )
  })

  it("treats the dynamic route parameter as the existing-session authority", () => {
    renderAppPage(<AgentSessionPage />, {
      projectContext: {
        activeConversationId: "session-old",
        conversationProjectId: "project-2",
      },
    })

    expect(screen.getByTestId("agent-workbench")).toHaveTextContent(
      "session:session-9|project:project-2",
    )
  })

  it("registers an icon-only desktop Workspace action in the global navbar", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Open workspace panel" })).not.toBeInTheDocument()
    expect(mocks.setNavbarActions).toHaveBeenCalled()

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const workspaceButton = screen.getByRole("button", {
      name: "Open workspace panel",
    })
    expect(workspaceButton).toHaveTextContent("")
    expect(workspaceButton).toHaveClass("h-8", "w-8")
    fireEvent.click(
      workspaceButton,
    )
    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
    fireEvent.click(workspaceButton)
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
  })

  it("restores an open desktop LiveDeck after reload", () => {
    localStorage.setItem("right-sidebar-collapsed", "false")

    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
  })

  it("offers the LiveDeck in a safe mobile sheet", () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    fireEvent.click(screen.getByRole("button", { name: "Open workspace panel" }))
    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
    expect(screen.getByRole("dialog")).toHaveClass("overscroll-contain")
    expect(screen.getByRole("dialog")).toHaveClass(
      "pb-[env(safe-area-inset-bottom)]",
    )
  })

  it("clears the global Workspace action when the Agent page unmounts", () => {
    const view = renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(mocks.setNavbarActions).toHaveBeenCalledWith(expect.anything())
    view.unmount()

    expect(mocks.setNavbarActions).toHaveBeenLastCalledWith(null)
  })

  it("opens a referenced run directly in the DAG workspace", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    fireEvent.click(screen.getByRole("button", { name: "Open referenced run" }))

    expect(screen.getByTestId("live-deck")).toHaveTextContent(
      "tab:dag|run:run-42",
    )
  })
})
