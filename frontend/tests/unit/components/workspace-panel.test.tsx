import { render, screen } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { AgentWorkspaceAdapter } from "@/lib/agent/workspace-adapter"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const copy: Record<string, string> = {
      loading: "Loading files",
      noFiles: "No files",
      "files.label": "Project file browser",
      "files.root": "workspace",
      "files.tree": "File tree",
      "files.filter": "Filter files",
      "files.select": "Select a file",
      "files.noProject": "No project selected",
      "files.noMatches": "No matching files",
      "files.download": "Download file",
      "files.refresh": "Refresh files",
      "preview.loading": "Loading preview",
      "preview.unable": "Unable to preview",
      "errors.loadFilesFailed": "Load files failed",
    }
    if (key === "files.truncated") return `Partial ${values?.count ?? 0}`
    return copy[key] ?? key
  },
}))

vi.mock("shiki", () => ({
  codeToHtml: vi.fn(async (content: string) => `<pre class="shiki"><code>${content}</code></pre>`),
}))

import { WorkspacePanel } from "@/components/bioinfoflow/workspace-panel"

function createAdapter(): AgentWorkspaceAdapter {
  return {
    listFiles: vi.fn(async () => []),
    readFile: vi.fn(async ({ path }) => ({
      path,
      content: "",
      totalLines: 0,
      truncated: false,
    })),
    fileDownloadUrl: vi.fn(() => "https://download.test/file"),
    listArtifacts: vi.fn(async () => []),
    getArtifact: vi.fn(async () => {
      throw new Error("unused")
    }),
    fetchArtifactContent: vi.fn(async () => {
      throw new Error("unused")
    }),
  }
}

describe("WorkspacePanel", () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it("shows the project-less state without calling the adapter", async () => {
    const adapter = createAdapter()
    render(<WorkspacePanel projectId={null} adapter={adapter} />)

    expect(await screen.findByText("No project selected")).toBeInTheDocument()
    expect(adapter.listFiles).not.toHaveBeenCalled()
  })

  it("keeps dotfiles visible and loads folder children on demand", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles)
      .mockResolvedValueOnce([
        { name: "results", path: "results", type: "directory", sizeBytes: null, modifiedAt: null },
        { name: ".env", path: ".env", type: "file", sizeBytes: 12, modifiedAt: null },
      ])
      .mockResolvedValueOnce([
        { name: "child.txt", path: "results/child.txt", type: "file", sizeBytes: 24, modifiedAt: null },
      ])

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    expect(await screen.findByText(".env")).toBeInTheDocument()
    await userEvent.click(screen.getByRole("button", { name: /results/i }))
    expect(await screen.findByText("child.txt")).toBeInTheDocument()
    expect(adapter.listFiles).toHaveBeenLastCalledWith({
      projectId: "project-1",
      path: "results",
    })
  })

  it("loads a selected file immediately and exposes its breadcrumb and download", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "report.json", path: "results/report.json", type: "file", sizeBytes: 24, modifiedAt: null },
    ])
    vi.mocked(adapter.readFile).mockResolvedValueOnce({
      path: "results/report.json",
      content: "{\"status\":\"ok\"}",
      totalLines: 1,
      truncated: false,
    })

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    await userEvent.click(await screen.findByRole("button", { name: /report.json/i }))
    expect(await screen.findByTestId("workspace-code-preview")).toHaveTextContent(
      '{"status":"ok"}',
    )
    expect(screen.getByText("results")).toBeInTheDocument()
    expect(screen.getAllByText("report.json")).toHaveLength(2)
    expect(screen.getByRole("link", { name: "Download file" })).toHaveAttribute(
      "href",
      "https://download.test/file",
    )
    expect(adapter.readFile).toHaveBeenCalledWith({
      projectId: "project-1",
      path: "results/report.json",
    })
  })

  it("filters the visible tree without adding extra panels", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "alpha.py", path: "alpha.py", type: "file", sizeBytes: 1, modifiedAt: null },
      { name: "beta.md", path: "beta.md", type: "file", sizeBytes: 1, modifiedAt: null },
    ])
    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    await screen.findByText("alpha.py")
    await userEvent.type(screen.getByRole("textbox", { name: "Filter files" }), "beta")
    expect(screen.queryByText("alpha.py")).not.toBeInTheDocument()
    expect(screen.getByText("beta.md")).toBeInTheDocument()
  })

  it("uses visible file-type colors for tree glyphs", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "config.json", path: "config.json", type: "file", sizeBytes: 1, modifiedAt: null },
      { name: "pipeline.nf", path: "pipeline.nf", type: "file", sizeBytes: 1, modifiedAt: null },
    ])

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    const jsonButton = await screen.findByRole("button", { name: /config.json/i })
    const codeButton = screen.getByRole("button", { name: /pipeline.nf/i })
    expect(jsonButton.querySelector("svg")).toHaveClass("text-amber-500")
    expect(codeButton.querySelector("svg")).toHaveClass("text-sky-500")
  })
})
