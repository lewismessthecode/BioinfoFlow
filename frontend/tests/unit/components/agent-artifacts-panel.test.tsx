import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { describe, expect, it, vi } from "vitest"

import type { AgentWorkspaceAdapter } from "@/lib/agent/workspace-adapter"

vi.mock("next-intl", () => ({
  useLocale: () => "en",
  useTranslations: () => (key: string) => {
    const copy: Record<string, string> = {
      label: "Agent artifacts",
      title: "Artifacts",
      preview: "Artifact preview",
      back: "Back to artifacts",
      download: "Download artifact",
      refresh: "Refresh artifacts",
      loading: "Loading artifacts",
      loadingPreview: "Loading preview",
      empty: "No artifacts yet",
      noSession: "Start a conversation to collect artifacts",
      loadFailed: "Could not load artifacts",
      previewFailed: "Could not load this artifact",
      previewUnavailable: "Preview unavailable",
      open: "Preview",
    }
    return copy[key] ?? key
  },
}))

vi.mock("shiki", () => ({
  codeToHtml: vi.fn(async (content: string) => `<pre class="shiki"><code>${content}</code></pre>`),
}))

import { AgentArtifactsPanel } from "@/components/bioinfoflow/agent-artifacts-panel"

function adapter(): AgentWorkspaceAdapter {
  return {
    listFiles: vi.fn(async () => []),
    readFile: vi.fn(async () => ({ path: "", content: "", totalLines: 0, truncated: false })),
    fileDownloadUrl: vi.fn(() => ""),
    listArtifacts: vi.fn(async () => [
      {
        id: "session:artifact-1",
        source: "session" as const,
        title: "qc-report.json",
        summary: "QC report",
        kind: "report",
        mediaType: "application/json",
        sizeBytes: 17,
        createdAt: "2026-08-17T00:00:00Z",
        updatedAt: "2026-08-17T00:00:00Z",
        payload: null,
        resource: {
          kind: "session" as const,
          artifactId: "artifact-1",
        },
      },
    ]),
    fetchArtifactContent: vi.fn(async () => ({
      blob: new Blob(['{"status":"ok"}'], { type: "application/json" }),
      filename: "qc-report.json",
      mediaType: "application/json",
    })),
  }
}

describe("AgentArtifactsPanel", () => {
  it("shows the session-less state without loading", () => {
    const workspaceAdapter = adapter()
    render(<AgentArtifactsPanel sessionId={null} adapter={workspaceAdapter} />)

    expect(screen.getByText("Start a conversation to collect artifacts")).toBeInTheDocument()
    expect(workspaceAdapter.listArtifacts).not.toHaveBeenCalled()
  })

  it("loads a compact artifact list and previews text inline", async () => {
    const workspaceAdapter = adapter()
    render(<AgentArtifactsPanel sessionId="session-1" adapter={workspaceAdapter} />)

    const card = await screen.findByRole("article", { name: "qc-report.json" })
    expect(card).toHaveTextContent("QC report")
    expect(card).toHaveTextContent("17 B")

    await userEvent.click(screen.getByRole("button", { name: "Preview qc-report.json" }))
    expect(await screen.findByTestId("workspace-code-preview")).toHaveTextContent(
      '{"status":"ok"}',
    )
    expect(workspaceAdapter.fetchArtifactContent).toHaveBeenCalledWith({
      artifact: expect.objectContaining({ id: "session:artifact-1" }),
    })
    expect(screen.getByRole("button", { name: "Back to artifacts" })).toBeInTheDocument()
  })

  it("opens the artifact selected by a transcript reference", async () => {
    const workspaceAdapter = adapter()
    render(
      <AgentArtifactsPanel
        sessionId="session-1"
        selectedArtifactId="artifact-1"
        adapter={workspaceAdapter}
      />,
    )

    expect(await screen.findByTestId("workspace-code-preview")).toHaveTextContent(
      '{"status":"ok"}',
    )
    expect(workspaceAdapter.fetchArtifactContent).toHaveBeenCalledWith({
      artifact: expect.objectContaining({ id: "session:artifact-1" }),
    })
  })

  it("shows and previews an HTML file discovered directly in the project", async () => {
    const workspaceAdapter = adapter()
    vi.mocked(workspaceAdapter.listArtifacts).mockResolvedValueOnce([
      {
        id: "workspace:project-1:index.html",
        source: "workspace",
        title: "index.html",
        summary: null,
        kind: "html",
        mediaType: "text/html",
        sizeBytes: 42,
        createdAt: "2026-08-17T01:00:00Z",
        updatedAt: "2026-08-17T01:00:00Z",
        payload: null,
        resource: {
          kind: "workspace",
          projectId: "project-1",
          path: "index.html",
        },
      },
    ])
    vi.mocked(workspaceAdapter.fetchArtifactContent).mockResolvedValueOnce({
      blob: new Blob(["<h1>BioinfoFlow</h1>"], { type: "text/html" }),
      filename: "index.html",
      mediaType: "text/html",
    })

    render(
      <AgentArtifactsPanel
        sessionId="session-1"
        projectId="project-1"
        adapter={workspaceAdapter}
      />,
    )

    await userEvent.click(await screen.findByRole("button", { name: /index.html/i }))
    const frame = await screen.findByTestId("artifact-html-preview")
    expect(frame).toHaveAttribute("sandbox", "")
    expect(frame).toHaveAttribute("srcdoc", "<h1>BioinfoFlow</h1>")
    expect(workspaceAdapter.listArtifacts).toHaveBeenCalledWith({
      sessionId: "session-1",
      projectId: "project-1",
      signal: expect.any(AbortSignal),
    })
  })
})
