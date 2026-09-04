import { render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type {
  AgentWorkspaceAdapter,
  WorkspaceFileNode,
  WorkspaceFilePreview,
} from "@/lib/agent/workspace-adapter"

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
      close: "Close",
      copy: "Copy",
      copiedToClipboard: "Copied to clipboard",
      "browser.openExternal": "Open in a new tab",
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
    fetchArtifactContent: vi.fn(async () => {
      throw new Error("unused")
    }),
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((nextResolve) => {
    resolve = nextResolve
  })
  return { promise, resolve }
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
      signal: expect.any(AbortSignal),
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
    expect(screen.getAllByText("report.json")).toHaveLength(3)
    expect(screen.getByRole("link", { name: "Download file" })).toHaveAttribute(
      "href",
      "https://download.test/file",
    )
    expect(adapter.readFile).toHaveBeenCalledWith({
      projectId: "project-1",
      path: "results/report.json",
      signal: expect.any(AbortSignal),
    })

    const selectedRow = screen.getByRole("button", { name: "report.json" })
    expect(selectedRow).toHaveAttribute("aria-current", "true")
    expect(selectedRow.querySelector('[data-file-accent="data"]')).not.toBeNull()
  })

  it("lets the selected file be opened externally and copied without changing the preview", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "notes.txt", path: "notes.txt", type: "file", sizeBytes: 24, modifiedAt: null },
    ])
    vi.mocked(adapter.readFile).mockResolvedValueOnce({
      path: "notes.txt",
      content: "hello from the workspace",
      totalLines: 1,
      truncated: false,
    })
    const writeText = vi.fn(async () => undefined)
    vi.stubGlobal("navigator", { clipboard: { writeText } })

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    await userEvent.click(await screen.findByRole("button", { name: /notes.txt/i }))
    expect(await screen.findByTestId("workspace-editor-file-header")).toBeInTheDocument()

    const externalLink = screen.getByRole("link", { name: "Open in a new tab" })
    expect(externalLink).toHaveAttribute("href", "https://download.test/file")
    expect(externalLink).toHaveAttribute("target", "_blank")
    expect(externalLink).toHaveAttribute("rel", "noreferrer")

    await userEvent.click(screen.getByRole("button", { name: "Copy" }))
    expect(writeText).toHaveBeenCalledWith("hello from the workspace")
    expect(screen.getByRole("button", { name: "Copied to clipboard" })).toBeInTheDocument()
  })

  it("disables external open when the adapter does not provide a safe file URL", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "notes.txt", path: "notes.txt", type: "file", sizeBytes: 24, modifiedAt: null },
    ])
    vi.mocked(adapter.fileDownloadUrl).mockReturnValueOnce("javascript:alert(1)")

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    await userEvent.click(await screen.findByRole("button", { name: "notes.txt" }))

    expect(screen.queryByRole("link", { name: "Open in a new tab" })).not.toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Open in a new tab" })).toBeDisabled()
  })

  it("shows the selected file as an editor tab that can be closed", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "report.json", path: "results/report.json", type: "file", sizeBytes: 24, modifiedAt: null },
    ])
    vi.mocked(adapter.readFile).mockResolvedValueOnce({
      path: "results/report.json",
      content: '{"status":"ok"}',
      totalLines: 1,
      truncated: false,
    })

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    await userEvent.click(await screen.findByRole("button", { name: /report.json/i }))
    expect(await screen.findByTestId("workspace-editor-file-header")).toBeInTheDocument()
    expect(screen.getByTestId("workspace-editor-file-tab")).toHaveTextContent("report.json")

    await userEvent.click(screen.getByRole("button", { name: "Close report.json" }))

    expect(screen.queryByTestId("workspace-editor-file-header")).not.toBeInTheDocument()
    expect(screen.queryByTestId("workspace-code-preview")).not.toBeInTheDocument()
    expect(screen.getByText("Select a file")).toBeInTheDocument()
  })

  it("uses a workbench header and keeps the editor wider than the file tree", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockResolvedValueOnce([
      { name: "pipeline.nf", path: "pipeline.nf", type: "file", sizeBytes: 24, modifiedAt: null },
    ])

    render(<WorkspacePanel projectId="project-1" adapter={adapter} />)

    expect(await screen.findByText("pipeline.nf")).toBeInTheDocument()
    expect(screen.getByTestId("workspace-panel-header")).toBeInTheDocument()
    expect(screen.getByTestId("workspace-editor-pane")).toBeInTheDocument()
    expect(screen.getByTestId("workspace-file-tree")).toBeInTheDocument()
    expect(screen.getByTestId("workspace-split-view")).toHaveAttribute(
      "data-layout",
      "editor-dominant",
    )
    expect(
      screen.getByRole("button", { name: /pipeline.nf/i }).querySelector(
        '[data-file-accent="code"]',
      ),
    ).not.toBeNull()
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

  it("ignores a stale tree response after the project changes", async () => {
    const adapter = createAdapter()
    const projectA = deferred<WorkspaceFileNode[]>()
    const projectB = deferred<WorkspaceFileNode[]>()
    vi.mocked(adapter.listFiles)
      .mockImplementationOnce(() => projectA.promise)
      .mockImplementationOnce(() => projectB.promise)

    const view = render(<WorkspacePanel projectId="project-a" adapter={adapter} />)
    await waitFor(() => expect(adapter.listFiles).toHaveBeenCalledTimes(1))
    view.rerender(<WorkspacePanel projectId="project-b" adapter={adapter} />)
    await waitFor(() => expect(adapter.listFiles).toHaveBeenCalledTimes(2))

    projectA.resolve([
      { name: "a.txt", path: "a.txt", type: "file", sizeBytes: 1, modifiedAt: null },
    ])
    projectB.resolve([
      { name: "b.txt", path: "b.txt", type: "file", sizeBytes: 1, modifiedAt: null },
    ])

    expect(await screen.findByText("b.txt")).toBeInTheDocument()
    expect(screen.queryByText("a.txt")).not.toBeInTheDocument()
    expect(vi.mocked(adapter.listFiles).mock.calls[0][0].signal?.aborted).toBe(true)
  })

  it("ignores a stale preview response after project replacement", async () => {
    const adapter = createAdapter()
    const preview = deferred<WorkspaceFilePreview>()
    vi.mocked(adapter.listFiles).mockImplementation(async ({ projectId }) => [
      {
        name: `${projectId}.txt`,
        path: `${projectId}.txt`,
        type: "file",
        sizeBytes: 1,
        modifiedAt: null,
      },
    ])
    vi.mocked(adapter.readFile).mockReturnValueOnce(preview.promise)

    const view = render(<WorkspacePanel projectId="project-a" adapter={adapter} />)
    await userEvent.click(await screen.findByRole("button", { name: /project-a.txt/i }))
    view.rerender(<WorkspacePanel projectId="project-b" adapter={adapter} />)

    preview.resolve({
      path: "project-a.txt",
      content: "stale project A content",
      totalLines: 1,
      truncated: false,
    })

    await waitFor(() => {
      expect(screen.queryByText("stale project A content")).not.toBeInTheDocument()
    })
    expect(vi.mocked(adapter.readFile).mock.calls[0][0].signal?.aborted).toBe(true)
  })

  it("clears the child loading spinner when its request is aborted", async () => {
    const adapter = createAdapter()
    const child = deferred<WorkspaceFileNode[]>()
    vi.mocked(adapter.listFiles).mockImplementation(async ({ path }) => {
      if (path === "results") return child.promise
      return [
        { name: "results", path: "results", type: "directory", sizeBytes: null, modifiedAt: null },
      ]
    })

    const view = render(<WorkspacePanel projectId="project-a" adapter={adapter} />)
    const results = await screen.findByRole("button", { name: /results/i })
    await userEvent.click(results)
    await waitFor(() =>
      expect(vi.mocked(adapter.listFiles)).toHaveBeenCalledWith(
        expect.objectContaining({ projectId: "project-a", path: "results" }),
      ),
    )

    view.rerender(<WorkspacePanel projectId="project-b" adapter={adapter} />)
    const nextResults = await screen.findByRole("button", { name: /results/i })
    expect(nextResults).toHaveAttribute("aria-expanded", "false")
    expect(nextResults.querySelector(".animate-spin")).not.toBeInTheDocument()
    expect(
      vi.mocked(adapter.listFiles).mock.calls.find(
        ([input]) => input.path === "results",
      )?.[0].signal?.aborted,
    ).toBe(true)
  })

  it("keeps the root tree visible when a child directory fails", async () => {
    const adapter = createAdapter()
    vi.mocked(adapter.listFiles).mockImplementation(async ({ path }) => {
      if (path === "results") throw new Error("child unavailable")
      return [
        { name: "results", path: "results", type: "directory", sizeBytes: null, modifiedAt: null },
        { name: "README.md", path: "README.md", type: "file", sizeBytes: 1, modifiedAt: null },
      ]
    })

    render(<WorkspacePanel projectId="project-a" adapter={adapter} />)
    await userEvent.click(await screen.findByRole("button", { name: /results/i }))

    expect(await screen.findByText("Load files failed")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: /README.md/i })).toBeInTheDocument()
    expect(screen.getAllByRole("button", { name: "Refresh files" })).toHaveLength(2)
  })

  it("keeps the spinner for a replacement child request", async () => {
    const adapter = createAdapter()
    const first = deferred<WorkspaceFileNode[]>()
    const replacement = deferred<WorkspaceFileNode[]>()
    let childRequest = 0
    vi.mocked(adapter.listFiles).mockImplementation(async ({ path }) => {
      if (path === "results") {
        childRequest += 1
        return childRequest === 1 ? first.promise : replacement.promise
      }
      return [
        { name: "results", path: "results", type: "directory", sizeBytes: null, modifiedAt: null },
      ]
    })

    render(<WorkspacePanel projectId="project-a" adapter={adapter} />)
    const results = await screen.findByRole("button", { name: /results/i })
    await userEvent.click(results)
    await waitFor(() => expect(childRequest).toBe(1))
    await userEvent.click(results)
    await userEvent.click(results)
    await waitFor(() => expect(childRequest).toBe(2))

    first.resolve([])
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /results/i }).querySelector(".animate-spin"))
        .toBeInTheDocument(),
    )

    replacement.resolve([])
    await waitFor(() =>
      expect(screen.getByRole("button", { name: /results/i }).querySelector(".animate-spin"))
        .not.toBeInTheDocument(),
    )
  })
})
