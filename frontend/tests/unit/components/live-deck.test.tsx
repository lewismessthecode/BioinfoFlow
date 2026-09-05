import { render, screen } from "@testing-library/react"
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
  it("renders only the active workspace surface without a duplicate surface tab bar", () => {
    const view = render(
      <LiveDeck
        activeTab="workspace"
        projectId="project-1"
        runId="run-1"
      />,
    )

    expect(screen.getByTestId("workspace-panel")).toBeInTheDocument()
    expect(screen.queryByTestId("live-deck-tab-bar")).not.toBeInTheDocument()
    expect(screen.queryByRole("tab", { name: "Files" })).not.toBeInTheDocument()

    view.rerender(
      <LiveDeck
        activeTab="dag"
        projectId="project-1"
        runId="run-1"
      />,
    )
    expect(screen.queryByTestId("workspace-panel")).not.toBeInTheDocument()
    expect(screen.getByTestId("dag-panel")).toBeInTheDocument()
  })

  it("renders the dag tab content without a duplicate collapse control", () => {
    render(
      <LiveDeck
        activeTab="dag"
        projectId="project-7"
        runId="run-7"
        workflowName="RNASeq"
      />,
    )

    expect(screen.getByTestId("dag-panel")).toHaveTextContent("project-7:run-7:RNASeq")
    expect(screen.queryByRole("button", { name: "Hide panel" })).not.toBeInTheDocument()
  })

  it("does not repeat the navbar Files, Workflow, Artifacts, and Browser actions", () => {
    render(
      <LiveDeck activeTab="workspace" projectId="project-1" />,
    )

    expect(screen.queryByText("Workflow")).not.toBeInTheDocument()
    expect(screen.queryByText("Artifacts")).not.toBeInTheDocument()
    expect(screen.queryByText("Browser")).not.toBeInTheDocument()
  })

  it("renders the requested surface directly", () => {
    render(
      <LiveDeck
        activeTab="artifacts"
        projectId="project-1"
      />,
    )

    expect(screen.getByTestId("artifacts-panel")).toBeInTheDocument()
    expect(screen.queryByTestId("workspace-panel")).not.toBeInTheDocument()
  })
})
