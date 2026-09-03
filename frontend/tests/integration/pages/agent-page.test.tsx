import { act, forwardRef, useImperativeHandle, type ReactNode } from "react"
import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import AgentSessionPage from "@/app/(app)/agent/[sessionId]/page"
import AgentPage, {
  AgentPageContent,
} from "@/app/(app)/agent/page"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { renderAppPage } from "@/tests/app-test-utils"

const mocks = vi.hoisted(() => ({
  params: vi.fn(() => ({ sessionId: "session-9" })),
  useEvents: vi.fn(),
  isMobile: vi.fn(() => false),
  workbench: vi.fn(),
  setNavbarActions: vi.fn(),
}))

function ProjectSwitcher() {
  const { selectWorkspaceProject } = useProjectContext()
  return (
    <button type="button" onClick={() => selectWorkspaceProject("project-b")}>
      switch project
    </button>
  )
}

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
      "workspacePanel.actions.openBrowser": "Open browser",
      "workspacePanel.actions.closeBrowser": "Close browser",
      "workspacePanel.actions.openFiles": "Open files",
      "workspacePanel.actions.closeFiles": "Close files",
      "workspacePanel.actions.openArtifacts": "Open artifacts",
      "workspacePanel.actions.closeArtifacts": "Close artifacts",
      "workspacePanel.actions.openDag": "Open DAG",
      "workspacePanel.actions.closeDag": "Close DAG",
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
      onOpenArtifact?: (artifactId: string) => void
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
        <button type="button" onClick={() => props.onOpenArtifact?.("artifact-42")}>
          Open referenced artifact
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
    selectedArtifactId,
    onSelectedArtifactIdChange,
    dag,
    onRunSelect,
  }: {
    onCollapse?: () => void
    activeTab: string
    runId?: string | null
    selectedArtifactId?: string | null
    onSelectedArtifactIdChange?: (artifactId: string | null) => void
    dag?: unknown
    onRunSelect?: (run: { run_id: string } | null) => void
  }) => (
    <div
      data-testid="live-deck"
      data-has-collapse={Boolean(onCollapse)}
      data-live-deck-focus-target
      tabIndex={0}
    >
      tab:{activeTab}|run:{runId ?? "none"}|artifact:{selectedArtifactId ?? "none"}|dag:
      {dag ? "present" : "none"}
      {onCollapse ? (
        <button type="button" onClick={onCollapse}>close</button>
      ) : null}
      <button
        type="button"
        data-testid="nested-escape-control"
        onKeyDown={(event) => {
          if (event.key === "Escape") event.preventDefault()
        }}
      >
        nested control
      </button>
      <button type="button" data-testid="select-run" onClick={() => onRunSelect?.({ run_id: "run-a" })}>
        select run
      </button>
      <button type="button" data-testid="select-artifact" onClick={() => onSelectedArtifactIdChange?.("artifact-99")}>
        select artifact
      </button>
    </div>
  ),
}))

vi.mock("@/components/ui/resize-handle", () => ({
  ResizeHandle: ({
    valueNow,
    valueMin,
    valueMax,
  }: {
    valueNow?: number
    valueMin?: number
    valueMax?: number
  }) => (
    <div
      data-testid="resize-handle"
      data-value-now={valueNow}
      data-value-min={valueMin}
      data-value-max={valueMax}
    />
  ),
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

  it("switches panel preferences when the session route changes", async () => {
    localStorage.setItem(
      "agent-panel:project-1:session-a",
      JSON.stringify({ activeTab: "artifacts", open: true, width: 500 }),
    )
    localStorage.setItem(
      "agent-panel:project-1:session-b",
      JSON.stringify({ activeTab: "browser", open: true, width: 350 }),
    )
    const view = renderAppPage(
      <AgentPageContent routeSessionId="session-a" />,
      { projectContext: { selectedProjectId: "project-1" } },
    )

    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:artifacts")
    expect(screen.getByTestId("agent-live-deck-rail")).toHaveAttribute(
      "data-width",
      "500",
    )

    view.rerender(
      <AgentPageContent routeSessionId="session-b" />,
    )
    await waitFor(() => {
      expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:browser")
      expect(screen.getByTestId("agent-live-deck-rail")).toHaveAttribute(
        "data-width",
        "350",
      )
    })
  })

  it("hands draft panel preferences to the resolved session", async () => {
    const draftPreferences = {
      activeTab: "artifacts",
      open: true,
      width: 520,
    }
    localStorage.setItem(
      "agent-panel:project-1:draft",
      JSON.stringify(draftPreferences),
    )

    renderAppPage(<AgentPageContent routeSessionId={null} />, {
      projectContext: { selectedProjectId: "project-1" },
    })
    const workbenchProps = mocks.workbench.mock.calls.at(-1)?.[0] as {
      onSessionResolved?: (session: {
        id: string
        projectId: string
        title: string
      }) => void
    }

    act(() => {
      workbenchProps.onSessionResolved?.({
        id: "session-new",
        projectId: "project-1",
        title: "New session",
      })
    })

    await waitFor(() => {
      expect(localStorage.getItem("agent-panel:project-1:session-new")).toBe(
        JSON.stringify(draftPreferences),
      )
    })
    expect(localStorage.getItem("agent-panel:project-1:draft")).toBeNull()
  })

  it("does not migrate draft preferences when opening an existing route", async () => {
    localStorage.setItem(
      "agent-panel:project-1:draft",
      JSON.stringify({ activeTab: "browser", open: true, width: 480 }),
    )
    const view = renderAppPage(<AgentPageContent routeSessionId={null} />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    view.rerender(<AgentPageContent routeSessionId="session-routed" />)

    expect(localStorage.getItem("agent-panel:project-1:session-routed")).toBeNull()
    expect(localStorage.getItem("agent-panel:project-1:draft")).toBe(
      JSON.stringify({ activeTab: "browser", open: true, width: 480 }),
    )
  })

  it("isolates run, artifact, and DAG state across session navigation", () => {
    localStorage.setItem(
      "agent-panel:project-1:session-a",
      JSON.stringify({ activeTab: "dag", open: true, width: 400 }),
    )
    localStorage.setItem(
      "agent-panel:project-1:session-b",
      JSON.stringify({ activeTab: "dag", open: true, width: 400 }),
    )
    const view = renderAppPage(
      <AgentPageContent routeSessionId="session-a" />,
      { projectContext: { selectedProjectId: "project-1" } },
    )

    fireEvent.click(screen.getByTestId("select-run"))
    fireEvent.click(screen.getByText("Open referenced artifact"))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("run:run-a")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:artifact-42")

    view.rerender(<AgentPageContent routeSessionId="session-b" />)

    expect(screen.getByTestId("live-deck")).toHaveTextContent("run:none")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:none")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("dag:none")

    fireEvent.click(screen.getByTestId("select-artifact"))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:artifact-99")
  })

  it("isolates transient run state when switching projects", () => {
    localStorage.setItem(
      "agent-panel:project-a:draft",
      JSON.stringify({ activeTab: "dag", open: true, width: 400 }),
    )
    localStorage.setItem(
      "agent-panel:project-b:draft",
      JSON.stringify({ activeTab: "dag", open: true, width: 400 }),
    )
    renderAppPage(
      <>
        <ProjectSwitcher />
        <AgentPageContent routeSessionId={null} />
      </>,
      { projectContext: { selectedProjectId: "project-a" } },
    )

    fireEvent.click(screen.getByTestId("select-run"))
    fireEvent.click(screen.getByText("Open referenced artifact"))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("run:run-a")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:artifact-42")

    fireEvent.click(screen.getByRole("button", { name: "switch project" }))

    expect(screen.getByTestId("live-deck")).toHaveTextContent("run:none")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:none")
    expect(screen.getByTestId("live-deck")).toHaveTextContent("dag:none")
    expect(mocks.useEvents.mock.calls.at(-1)?.[0]).toEqual(
      expect.objectContaining({ projectId: "project-b" }),
    )

    fireEvent.click(screen.getByTestId("select-run"))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("run:run-a")
    fireEvent.click(screen.getByTestId("select-artifact"))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("artifact:artifact-99")
  })

  it("keeps draft preferences when the active session resets to an empty id", () => {
    const draftPreferences = { activeTab: "dag", open: true, width: 560 }
    localStorage.setItem(
      "agent-panel:project-1:draft",
      JSON.stringify(draftPreferences),
    )
    renderAppPage(<AgentPageContent routeSessionId={null} />, {
      projectContext: { selectedProjectId: "project-1" },
    })
    const workbenchProps = mocks.workbench.mock.calls.at(-1)?.[0] as {
      onActiveSessionIdChange?: (sessionId: string) => void
    }

    act(() => workbenchProps.onActiveSessionIdChange?.(""))

    expect(localStorage.getItem("agent-panel:project-1:draft")).toBe(
      JSON.stringify(draftPreferences),
    )
    expect(localStorage.getItem("agent-panel:project-1:")).toBeNull()
  })

  it("registers independent desktop actions for every workspace surface", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    expect(
      screen.queryByRole("button", { name: "Open workspace panel" }),
    ).not.toBeInTheDocument()
    expect(mocks.setNavbarActions).toHaveBeenCalled()

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    expect(screen.getByRole("button", { name: "Open browser" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Open files" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Open artifacts" })).toBeVisible()
    expect(screen.getByRole("button", { name: "Open DAG" })).toBeVisible()
    expect(screen.queryByText("Subagents")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Open browser" }))
    expect(screen.getByTestId("live-deck")).toHaveAttribute(
      "data-has-collapse",
      "true",
    )
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:browser")

    fireEvent.click(screen.getByRole("button", { name: "Open files" }))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:workspace")
    fireEvent.click(screen.getByRole("button", { name: "Open artifacts" }))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:artifacts")
    fireEvent.click(screen.getByRole("button", { name: "Open DAG" }))
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:dag")

    fireEvent.keyDown(window, { key: "Escape" })
    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
  })

  it("persists active tab and open state per project draft", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    fireEvent.click(screen.getByRole("button", { name: "Open artifacts" }))

    expect(localStorage.getItem("agent-panel:project-1:draft")).toBe(
      JSON.stringify({ activeTab: "artifacts", open: true, width: 400 }),
    )
  })

  it("keeps the panel storage listener bound across panel updates", async () => {
    const addEventListener = vi.spyOn(window, "addEventListener")
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    await waitFor(() => {
      expect(
        addEventListener.mock.calls.filter(([type]) => type === "storage"),
      ).toHaveLength(1)
    })

    fireEvent.click(screen.getByRole("button", { name: "Open artifacts" }))
    fireEvent.click(screen.getByTestId("agent-action-artifacts"))
    expect(
      addEventListener.mock.calls.filter(([type]) => type === "storage"),
    ).toHaveLength(1)
    addEventListener.mockRestore()
  })

  it("does not close LiveDeck when a nested control consumes Escape", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    fireEvent.click(screen.getByRole("button", { name: "Open files" }))
    fireEvent.keyDown(screen.getByTestId("nested-escape-control"), {
      key: "Escape",
    })

    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
  })

  it("clamps a restored desktop rail to the supported width range", () => {
    localStorage.setItem(
      "agent-panel:project-1:draft",
      JSON.stringify({ activeTab: "artifacts", open: true, width: 900 }),
    )

    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const rail = screen.getByTestId("agent-live-deck-rail")
    expect(rail).toHaveAttribute("data-width", "600")
    expect(rail).toHaveStyle({ width: "600px" })
    expect(screen.getByTestId("live-deck")).toHaveAttribute(
      "data-has-collapse",
      "true",
    )
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:artifacts")
  })

  it("offers the LiveDeck in a safe mobile sheet", () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    expect(screen.queryByTestId("live-deck")).not.toBeInTheDocument()
    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    fireEvent.click(screen.getByRole("button", { name: "Open files" }))
    expect(screen.getByTestId("live-deck")).toBeInTheDocument()
    expect(screen.getByTestId("live-deck")).toHaveAttribute(
      "data-has-collapse",
      "true",
    )
    expect(screen.getByRole("dialog")).toHaveClass("overscroll-contain")
    expect(screen.getByRole("dialog")).toHaveClass(
      "pb-[env(safe-area-inset-bottom)]",
    )
  })

  it("restores focus to the mobile action after Escape closes the sheet", async () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const filesButton = screen.getByRole("button", { name: "Open files" })
    fireEvent.click(filesButton)
    fireEvent.blur(filesButton)
    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => expect(filesButton).toHaveFocus())
  })

  it("opens and closes the mobile sheet from the panel keyboard shortcut", async () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const filesButton = screen.getByRole("button", { name: "Open files" })
    fireEvent.keyDown(window, {
      key: "b",
      ctrlKey: true,
      shiftKey: true,
    })
    expect(screen.getByRole("dialog")).toBeInTheDocument()
    screen.getByTestId("live-deck").focus()
    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => expect(filesButton).toHaveFocus())
  })

  it("returns desktop rail focus to the selected navbar action on Escape and shortcut close", async () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const filesButton = screen.getByRole("button", { name: "Open files" })
    fireEvent.click(filesButton)
    const focusTarget = screen.getByTestId("live-deck")
    focusTarget.focus()
    fireEvent.keyDown(window, { key: "Escape" })
    await waitFor(() => expect(filesButton).toHaveFocus())

    fireEvent.click(filesButton)
    screen.getByTestId("live-deck").focus()
    fireEvent.keyDown(window, {
      key: "b",
      ctrlKey: true,
      shiftKey: true,
    })
    await waitFor(() => expect(filesButton).toHaveFocus())
  })

  it("returns a referenced run opener after closing its mobile sheet", async () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const staleAction = screen.getByRole("button", { name: "Open files" })
    fireEvent.click(staleAction)
    fireEvent.keyDown(window, { key: "Escape" })
    await waitFor(() => expect(staleAction).toHaveFocus())

    const opener = screen.getByRole("button", { name: "Open referenced run" })
    opener.focus()
    fireEvent.click(opener)
    expect(screen.getByTestId("live-deck")).toHaveTextContent("tab:dag|run:run-42")
    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => expect(opener).toHaveFocus())
  })

  it("returns a referenced artifact opener after closing its mobile sheet", async () => {
    mocks.isMobile.mockReturnValue(true)
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const navbarAction = mocks.setNavbarActions.mock.calls.at(-1)?.[0] as ReactNode
    render(<>{navbarAction}</>)
    const staleAction = screen.getByRole("button", { name: "Open files" })
    fireEvent.click(staleAction)
    fireEvent.keyDown(window, { key: "Escape" })
    await waitFor(() => expect(staleAction).toHaveFocus())

    const opener = screen.getByRole("button", { name: "Open referenced artifact" })
    opener.focus()
    fireEvent.click(opener)
    expect(screen.getByTestId("live-deck")).toHaveTextContent(
      "tab:artifacts|run:none|artifact:artifact-42",
    )
    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => expect(opener).toHaveFocus())
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

  it("preserves a connected referenced opener when desktop Escape closes the rail", async () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    const opener = screen.getByRole("button", { name: "Open referenced run" })
    opener.focus()
    fireEvent.click(opener)
    screen.getByTestId("live-deck").focus()
    fireEvent.keyDown(window, { key: "Escape" })

    await waitFor(() => expect(opener).toHaveFocus())
  })

  it("opens a transcript artifact directly in the artifact workspace", () => {
    renderAppPage(<AgentPage />, {
      projectContext: { selectedProjectId: "project-1" },
    })

    fireEvent.click(
      screen.getByRole("button", { name: "Open referenced artifact" }),
    )

    expect(screen.getByTestId("live-deck")).toHaveTextContent(
      "tab:artifacts|run:none|artifact:artifact-42",
    )
  })
})
