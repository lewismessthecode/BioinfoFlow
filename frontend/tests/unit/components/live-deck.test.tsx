import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

vi.mock("next-intl", () => ({
  useTranslations: (namespace: string) => (key: string) => {
    const copy: Record<string, Record<string, string>> = {
      workspace: {
        "liveDeck.files": "Files",
        "liveDeck.pipeline": "Pipeline",
        "liveDeck.monitor": "Monitor",
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

vi.mock("@/components/bioinfoflow/monitor-panel", () => ({
  MonitorPanel: () => <div data-testid="monitor-panel">monitor panel</div>,
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
    await user.click(screen.getByRole("tab", { name: "Pipeline" }))
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
    await user.click(screen.getByRole("button", { name: "Hide panel" }))
    expect(onCollapse).toHaveBeenCalledTimes(1)
  })

  it("renders the monitor tab content", () => {
    render(
      <LiveDeck activeTab="monitor" onTabChange={vi.fn()} projectId="project-1" />,
    )

    expect(screen.getByTestId("monitor-panel")).toBeInTheDocument()
  })
})
