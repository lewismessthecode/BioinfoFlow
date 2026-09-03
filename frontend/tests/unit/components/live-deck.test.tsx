import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, Record<string, string>> = {
      workspace: {
        "liveDeck.files": "Files",
        "liveDeck.pipeline": "Workflow",
        "liveDeck.artifacts": "Artifacts",
        "liveDeck.browser": "Browser",
      },
      accessibility: {
        hidePanel: "Hide panel",
      },
    }
    return copy[namespace]?.[key] ?? key
  },
}))

vi.mock("@/components/bioinfoflow/workspace-panel", () => ({
  WorkspacePanel: () => <div data-testid="workspace-panel">workspace panel</div>,
}))

vi.mock("@/components/bioinfoflow/agent-artifacts-panel", () => ({
  AgentArtifactsPanel: () => <div data-testid="artifacts-panel">artifacts panel</div>,
}))

vi.mock("@/components/bioinfoflow/agent-browser-panel", () => ({
  AgentBrowserPanel: () => <div data-testid="browser-panel">browser panel</div>,
}))

vi.mock("@/components/bioinfoflow/dag", () => ({
  DagPanel: ({
    projectId,
    runId,
    workflowName,
  }: {
    projectId?: string | null
    runId?: string | null
    workflowName?: string
  }) => (
    <div data-testid="dag-panel">
      {projectId}:{runId}:{workflowName}
    </div>
  ),
}))

vi.mock("@/components/bioinfoflow/chat/chat-error-boundary", () => ({
  ChatErrorBoundary: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

import { LiveDeck } from "@/components/bioinfoflow/live-deck"

describe("LiveDeck", () => {
  it("renders the active workspace tab and lets the user request a tab change", async () => {
    const user = userEvent.setup()
    const onTabChange = vi.fn()

    render(
      <LiveDeck
        activeTab="workspace"
        onTabChange={onTabChange}
        projectId="project-1"
        runId="run-1"
      />,
    )

    expect(screen.getByTestId("workspace-panel")).toBeInTheDocument()
    await user.click(screen.getByRole("tab", { name: "Workflow" }))
    expect(onTabChange).toHaveBeenCalledWith("dag")
  })

  it("renders the dag tab content and forwards the collapse action", async () => {
    const user = userEvent.setup()
    const onCollapse = vi.fn()

    render(
      <LiveDeck
        activeTab="dag"
        onTabChange={vi.fn()}
        onCollapse={onCollapse}
        projectId="project-7"
        runId="run-7"
        workflowName="RNASeq"
      />,
    )

    expect(screen.getByTestId("dag-panel")).toHaveTextContent("project-7:run-7:RNASeq")
    const hideButton = screen.getByRole("button", { name: "Hide panel" })
    expect(hideButton).toHaveClass("size-11", "min-[1025px]:size-9")
    await user.click(hideButton)
    expect(onCollapse).toHaveBeenCalledTimes(1)
  })

  it("offers files, workflow, artifacts, and browser tabs", () => {
    render(
      <LiveDeck activeTab="workspace" onTabChange={vi.fn()} projectId="project-1" />,
    )

    expect(screen.getAllByRole("tab")).toHaveLength(4)
    expect(screen.getByRole("tab", { name: "Files" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Workflow" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Artifacts" })).toBeInTheDocument()
    expect(screen.getByRole("tab", { name: "Browser" })).toBeInTheDocument()
  })

  it("marks only the selected tab active and preserves the compact divider", () => {
    render(
      <LiveDeck
        activeTab="artifacts"
        onTabChange={vi.fn()}
        projectId="project-1"
      />,
    )

    expect(screen.getByRole("tab", { name: "Artifacts" })).toHaveAttribute(
      "data-state",
      "active",
    )
    expect(screen.getByRole("tab", { name: "Files" })).toHaveAttribute(
      "data-state",
      "inactive",
    )
    expect(screen.getByTestId("live-deck-tab-bar")).toHaveClass(
      "border-b",
      "min-h-11",
    )
  })
})
