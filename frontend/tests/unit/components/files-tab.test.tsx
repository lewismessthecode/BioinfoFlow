import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FilesTab } from "@/components/bioinfoflow/agent-runtime/files-tab"
import {
  buildAgentFsDownloadUrl,
  getAgentFsFile,
  getAgentFsTree,
  type AgentFsFile,
  type AgentFsTree,
} from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const labels: Record<string, string> = {
      "files.title": "Project files",
      "files.refresh": "Refresh",
      "files.empty": "No files",
      "files.error": "Could not load files",
      "files.up": "Up",
      "files.back": "Back",
      "files.selectPreview": "Select a file to preview",
      "files.truncated": "File truncated",
      "files.search": "Search loaded files",
      "files.clearSearch": "Clear search",
      "files.collapseAll": "Collapse all",
      "files.closePreview": "Close preview",
      "files.resizeTree": "Resize file tree",
      "files.loadedOnly": `${values?.count ?? 0} loaded items`,
      "files.loading": "Loading...",
      "files.addToContext": "Add to context",
      "files.copyPath": "Copy path",
      "files.download": "Download",
      "files.openDefault": "Open",
      "files.previewUnavailable": "Preview unavailable",
      "files.previewUnsupported": "Preview unsupported",
      "files.openDefaultDescription": "Open or download the file",
      "renderer.previewUnavailable": "Preview unavailable",
      "renderer.previewUnsupported": "Preview unsupported",
      "renderer.openDefaultDescription": "Open or download the file",
      "renderer.noRenderableSource": "No renderable source",
      "renderer.defaultSheetName": "Sheet",
      "renderer.previewLimit": `${values?.rows ?? 0} rows · ${values?.columns ?? 0} columns shown`,
      "renderer.workbookLoading": "Loading workbook",
      "renderer.workbookLoadingDescription": "Preparing workbook preview",
      "renderer.workbookFetchFailed": "Could not download workbook",
      "renderer.workbookFailed": "Could not preview workbook",
      "renderer.workbookEmpty": "Workbook has no visible rows",
      "renderer.workbookEmptyDescription": "Open in spreadsheet app",
      "renderer.workbookTooLarge": "Workbook too large",
      "renderer.kinds.markdown": "Markdown",
      "renderer.kinds.html": "HTML",
      "renderer.kinds.pdf": "PDF",
      "renderer.kinds.image": "Image",
      "renderer.kinds.spreadsheet": "Spreadsheet",
      "renderer.kinds.json": "JSON",
      "renderer.kinds.text": "Text",
      "renderer.kinds.unsupported": "File",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/lib/agent-runtime", () => ({
  getAgentFsTree: vi.fn(),
  getAgentFsFile: vi.fn(),
  buildAgentFsDownloadUrl: vi.fn((path: string, options?: { inline?: boolean }) =>
    `/agent/fs/download?path=${encodeURIComponent(path)}${options?.inline ? "&inline=true" : ""}`,
  ),
}))

const rootPath = "/data/projects/project-1"
const srcPath = `${rootPath}/src`
const workflowPath = `${rootPath}/workflow.wdl`
const scriptPath = `${srcPath}/main.nf`

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((next) => {
    resolve = next
  })
  return { promise, resolve }
}

describe("FilesTab", () => {
  beforeEach(() => {
    vi.mocked(getAgentFsTree).mockReset()
    vi.mocked(getAgentFsFile).mockReset()
    vi.mocked(buildAgentFsDownloadUrl).mockClear()
    window.localStorage.removeItem("agent-files-tree-width")
    vi.mocked(getAgentFsTree).mockImplementation(async (path) => {
      if (path === srcPath) {
        return {
          path: srcPath,
          entries: [{ name: "main.nf", path: scriptPath, type: "file" }],
        }
      }
      return {
        path: rootPath,
        entries: [
          { name: "src", path: srcPath, type: "dir" },
          { name: "workflow.wdl", path: workflowPath, type: "file" },
        ],
      }
    })
    vi.mocked(getAgentFsFile).mockImplementation(async (path) => ({
      path,
      content: path.endsWith("main.nf") ? "nextflow content" : "workflow content",
      truncated: false,
      size: 16,
      language: path.endsWith("main.nf") ? "nextflow" : "wdl",
    }))
  })

  it("loads the project root when opened with a project id", async () => {
    render(<FilesTab projectId="project-1" />)

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(null, "project-1")
    })
    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
    expect(screen.getByText(rootPath)).toBeInTheDocument()
  })

  it("expands and collapses directories without discarding cached children", async () => {
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(srcPath, "project-1")
    })
    expect(await screen.findByText("main.nf")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(screen.getByText("main.nf")).toBeInTheDocument()
    expect(getAgentFsTree).toHaveBeenCalledTimes(2)
  })

  it("previews files without replacing the loaded tree", async () => {
    const onAddContext = vi.fn()
    render(<FilesTab projectId="project-1" onAddContext={onAddContext} />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))
    fireEvent.click(await screen.findByRole("button", { name: "main.nf" }))

    await waitFor(() => {
      expect(getAgentFsFile).toHaveBeenCalledWith(scriptPath)
    })
    expect(await screen.findByTestId("agent-file-preview")).toBeInTheDocument()
    expect(screen.getByText("nextflow content")).toBeInTheDocument()
    expect(screen.getByTestId("agent-workspace-tree")).toBeInTheDocument()
    expect(screen.getByTestId("files-tab-split")).toBeInTheDocument()
    expect(screen.getByTestId("file-preview-pane")).toContainElement(
      screen.getByTestId("agent-file-preview"),
    )
    expect(screen.getByTestId("file-tree-pane")).toContainElement(
      screen.getByTestId("agent-workspace-tree"),
    )
    expect(screen.getByRole("separator", { name: "Resize file tree" })).toHaveAttribute(
      "aria-valuenow",
      "280",
    )
    expect(screen.getByText("src")).toBeInTheDocument()
    expect(within(screen.getByTestId("file-tree-pane")).getByText("main.nf")).toBeInTheDocument()

    const addButtons = within(screen.getByTestId("file-preview-pane")).getAllByRole("button", {
      name: "Add to context",
    })
    fireEvent.click(addButtons.at(-1)!)
    expect(onAddContext).toHaveBeenCalledWith(scriptPath)
  })

  it("renders markdown, html, pdf, and csv files with native preview affordances", async () => {
    const markdownPath = `${rootPath}/report.md`
    const htmlPath = `${rootPath}/report.html`
    const pdfPath = `${rootPath}/summary.pdf`
    const csvPath = `${rootPath}/metrics.csv`
    vi.mocked(getAgentFsTree).mockResolvedValue({
      path: rootPath,
      entries: [
        { name: "report.md", path: markdownPath, type: "file" },
        { name: "report.html", path: htmlPath, type: "file" },
        { name: "summary.pdf", path: pdfPath, type: "file" },
        { name: "metrics.csv", path: csvPath, type: "file" },
      ],
    })
    vi.mocked(getAgentFsFile).mockImplementation(async (path) => {
      if (path === markdownPath) {
        return {
          path,
          content: "# QC Report",
          truncated: false,
          size: 12,
          language: "markdown",
          mime_type: "text/markdown",
        }
      }
      if (path === htmlPath) {
        return {
          path,
          content: "<h1>Interactive report</h1>",
          truncated: false,
          size: 28,
          language: "html",
          mime_type: "text/html",
        }
      }
      if (path === pdfPath) {
        return {
          path,
          content: "",
          truncated: false,
          size: 2048,
          language: "pdf",
          mime_type: "application/pdf",
          binary: true,
        }
      }
      return {
        path,
        content: "sample,reads\nA,42",
        truncated: false,
        size: 17,
        language: "csv",
        mime_type: "text/csv",
      }
    })

    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "report.md" }))
    expect(await screen.findByRole("heading", { name: "QC Report" })).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "report.html" }))
    await waitFor(() => {
      expect(screen.getByTestId("file-preview-pane").querySelector("iframe")).toHaveAttribute(
        "title",
        "report.html",
      )
    })
    const htmlFrame = screen.getByTestId("file-preview-pane").querySelector("iframe")
    expect(htmlFrame).toHaveAttribute("sandbox", "")
    expect(htmlFrame).toHaveAttribute("srcdoc", "<h1>Interactive report</h1>")

    fireEvent.click(screen.getByRole("button", { name: "summary.pdf" }))
    await waitFor(() => {
      expect(screen.getByTestId("file-preview-pane").querySelector("iframe")).toHaveAttribute(
        "title",
        "summary.pdf",
      )
    })
    expect(screen.getByTestId("file-preview-pane").querySelector("iframe")).toHaveAttribute(
      "src",
      buildAgentFsDownloadUrl(pdfPath, { inline: true }),
    )
    expect(buildAgentFsDownloadUrl).toHaveBeenCalledWith(pdfPath, { inline: true })

    fireEvent.click(screen.getByRole("button", { name: "metrics.csv" }))
    expect(await screen.findByRole("table")).toHaveTextContent("reads")
    expect(screen.getByRole("table")).toHaveTextContent("42")
  })

  it("offers a fallback for unsupported binary files", async () => {
    const binaryPath = `${rootPath}/reads.bam`
    vi.mocked(getAgentFsTree).mockResolvedValue({
      path: rootPath,
      entries: [{ name: "reads.bam", path: binaryPath, type: "file" }],
    })
    vi.mocked(getAgentFsFile).mockResolvedValue({
      path: binaryPath,
      content: "",
      truncated: false,
      size: 4096,
      language: null,
      mime_type: "application/octet-stream",
      binary: true,
    })

    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "reads.bam" }))
    expect(await screen.findByText("Preview unsupported")).toBeInTheDocument()
    expect(screen.getByRole("link", { name: /Open/ })).toHaveAttribute(
      "href",
      `/agent/fs/download?path=${encodeURIComponent(binaryPath)}`,
    )
  })

  it("keeps an empty preview pane beside the file tree before a file is selected", async () => {
    render(<FilesTab projectId="project-1" />)

    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
    expect(screen.getByTestId("files-tab-split")).toBeInTheDocument()
    expect(screen.getByTestId("file-preview-pane")).toHaveTextContent(
      "Select a file to preview",
    )
    expect(screen.getByTestId("file-tree-pane")).toContainElement(
      screen.getByTestId("agent-workspace-tree"),
    )
  })

  it("resizes the file tree with keyboard and pointer controls", async () => {
    render(<FilesTab projectId="project-1" />)

    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
    const split = screen.getByTestId("files-tab-split")
    vi.spyOn(split, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      right: 900,
      top: 0,
      bottom: 600,
      width: 900,
      height: 600,
      toJSON: () => ({}),
    })
    const resizer = screen.getByRole("separator", { name: "Resize file tree" })

    fireEvent.keyDown(resizer, { key: "ArrowLeft" })
    expect(resizer).toHaveAttribute("aria-valuenow", "304")

    fireEvent.pointerDown(resizer, { clientX: 520 })
    fireEvent.pointerMove(window, { clientX: 500 })
    fireEvent.pointerUp(window)

    await waitFor(() => {
      expect(resizer).toHaveAttribute("aria-valuenow", "400")
    })
    expect(window.localStorage.getItem("agent-files-tree-width")).toBe("400")
  })

  it("clamps keyboard and stored tree widths to preserve preview space", async () => {
    window.localStorage.setItem("agent-files-tree-width", "520")
    render(<FilesTab projectId="project-1" />)

    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
    const split = screen.getByTestId("files-tab-split")
    vi.spyOn(split, "getBoundingClientRect").mockReturnValue({
      x: 0,
      y: 0,
      left: 0,
      right: 680,
      top: 0,
      bottom: 600,
      width: 680,
      height: 600,
      toJSON: () => ({}),
    })
    await act(async () => {
      window.dispatchEvent(new Event("resize"))
    })

    const resizer = screen.getByRole("separator", { name: "Resize file tree" })
    await waitFor(() => {
      expect(resizer).toHaveAttribute("aria-valuenow", "312")
    })

    fireEvent.keyDown(resizer, { key: "End" })
    expect(resizer).toHaveAttribute("aria-valuenow", "312")
  })

  it("filters only loaded nodes and reveals collapsed matching descendants", async () => {
    render(<FilesTab projectId="project-1" />)

    fireEvent.change(await screen.findByPlaceholderText("Search loaded files"), {
      target: { value: "main" },
    })
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Search loaded files"), {
      target: { value: "" },
    })
    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(await screen.findByText("main.nf")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()

    fireEvent.change(screen.getByPlaceholderText("Search loaded files"), {
      target: { value: "main" },
    })
    expect(screen.getByText("main.nf")).toBeInTheDocument()
    expect(screen.queryByText("workflow.wdl")).not.toBeInTheDocument()
  })

  it("offers an accessible search box with a clear control", async () => {
    render(<FilesTab projectId="project-1" />)

    const search = await screen.findByRole("searchbox", { name: "Search loaded files" })
    fireEvent.change(search, { target: { value: "workflow" } })

    expect(screen.getByText("workflow.wdl")).toBeInTheDocument()
    expect(screen.queryByText("src")).not.toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Clear search" }))

    expect(search).toHaveValue("")
    expect(screen.getByText("src")).toBeInTheDocument()
  })

  it("marks selected files and exposes extension-aware row kinds", async () => {
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "workflow.wdl" }))
    expect(await screen.findByText("workflow content")).toBeInTheDocument()

    const rowButton = screen.getByRole("button", { name: "workflow.wdl" })
    const row = rowButton.closest("[data-file-kind='workflow']")
    expect(rowButton).toHaveAttribute("aria-current", "true")
    expect(row).toHaveAttribute("data-selected", "true")
    expect(row).toHaveAttribute("data-file-kind", "workflow")
  })

  it("collapses all expanded directories without clearing cached children", async () => {
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))
    expect(await screen.findByText("main.nf")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Collapse all" }))

    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(screen.getByText("main.nf")).toBeInTheDocument()
    expect(getAgentFsTree).toHaveBeenCalledTimes(2)
  })

  it("clears cached children and previews when the project changes", async () => {
    vi.mocked(getAgentFsTree).mockImplementation(async (path, projectId) => {
      if (projectId === "project-2") {
        return {
          path: "/data/projects/project-2",
          entries: [{ name: "other.wdl", path: "/data/projects/project-2/other.wdl", type: "file" }],
        }
      }
      if (path === srcPath) {
        return {
          path: srcPath,
          entries: [{ name: "main.nf", path: scriptPath, type: "file" }],
        }
      }
      return {
        path: rootPath,
        entries: [{ name: "src", path: srcPath, type: "dir" }],
      }
    })
    const { rerender } = render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))
    fireEvent.click(await screen.findByRole("button", { name: "main.nf" }))
    expect(await screen.findByText("nextflow content")).toBeInTheDocument()

    rerender(<FilesTab projectId="project-2" />)

    expect(await screen.findByText("other.wdl")).toBeInTheDocument()
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()
    expect(screen.queryByTestId("agent-file-preview")).not.toBeInTheDocument()
  })

  it("ignores stale tree responses when the project changes", async () => {
    const projectOneRoot = deferred<AgentFsTree>()
    vi.mocked(getAgentFsTree).mockImplementation((path, projectId) => {
      if (projectId === "project-1" && path === null) return projectOneRoot.promise
      if (projectId === "project-2" && path === null) {
        return Promise.resolve({
          path: "/data/projects/project-2",
          entries: [{ name: "other.wdl", path: "/data/projects/project-2/other.wdl", type: "file" }],
        })
      }
      return Promise.resolve({ path: String(path ?? ""), entries: [] })
    })
    const { rerender } = render(<FilesTab projectId="project-1" />)

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(null, "project-1")
    })
    rerender(<FilesTab projectId="project-2" />)

    expect(await screen.findByText("other.wdl")).toBeInTheDocument()
    await act(async () => {
      projectOneRoot.resolve({
        path: rootPath,
        entries: [{ name: "stale.wdl", path: `${rootPath}/stale.wdl`, type: "file" }],
      })
    })

    expect(screen.queryByText("stale.wdl")).not.toBeInTheDocument()
    expect(screen.getByText("/data/projects/project-2")).toBeInTheDocument()
  })

  it("ignores older same-project tree responses after a newer refresh", async () => {
    const firstRoot = deferred<AgentFsTree>()
    const refreshedRoot = deferred<AgentFsTree>()
    vi.mocked(getAgentFsTree).mockImplementation((path) => {
      if (path === null) {
        const rootRequestCount = vi
          .mocked(getAgentFsTree)
          .mock.calls.filter(([requestedPath]) => requestedPath === null).length
        return rootRequestCount === 1 ? firstRoot.promise : refreshedRoot.promise
      }
      return Promise.resolve({ path: String(path ?? ""), entries: [] })
    })
    render(<FilesTab projectId="project-1" />)

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(null, "project-1")
    })
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }))

    await act(async () => {
      refreshedRoot.resolve({
        path: rootPath,
        entries: [{ name: "fresh.wdl", path: `${rootPath}/fresh.wdl`, type: "file" }],
      })
    })
    expect(await screen.findByText("fresh.wdl")).toBeInTheDocument()

    await act(async () => {
      firstRoot.resolve({
        path: rootPath,
        entries: [{ name: "stale.wdl", path: `${rootPath}/stale.wdl`, type: "file" }],
      })
    })
    expect(screen.queryByText("stale.wdl")).not.toBeInTheDocument()
  })

  it("refreshes cached children even when their directory is collapsed", async () => {
    let childEntries = [{ name: "main.nf", path: scriptPath, type: "file" as const }]
    vi.mocked(getAgentFsTree).mockImplementation(async (path) => {
      if (path === srcPath) return { path: srcPath, entries: childEntries }
      return {
        path: rootPath,
        entries: [{ name: "src", path: srcPath, type: "dir" }],
      }
    })
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))
    expect(await screen.findByText("main.nf")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()

    childEntries = [{ name: "updated.nf", path: `${srcPath}/updated.nf`, type: "file" }]
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }))
    await waitFor(() => {
      expect(
        vi.mocked(getAgentFsTree).mock.calls.filter(([path]) => path === srcPath),
      ).toHaveLength(2)
    })

    fireEvent.click(screen.getByRole("button", { name: "src" }))
    expect(await screen.findByText("updated.nf")).toBeInTheDocument()
    expect(screen.queryByText("main.nf")).not.toBeInTheDocument()
  })

  it("refreshes the selected file preview", async () => {
    let workflowContent = "workflow content"
    vi.mocked(getAgentFsFile).mockImplementation(async (path) => ({
      path,
      content: workflowContent,
      truncated: false,
      size: workflowContent.length,
      language: "wdl",
    }))
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "workflow.wdl" }))
    expect(await screen.findByText("workflow content")).toBeInTheDocument()

    workflowContent = "updated workflow content"
    fireEvent.click(screen.getByRole("button", { name: "Refresh" }))

    expect(await screen.findByText("updated workflow content")).toBeInTheDocument()
    expect(screen.queryByText("workflow content")).not.toBeInTheDocument()
  })

  it("ignores stale file preview responses", async () => {
    const mainRequest = deferred<AgentFsFile>()
    const workflowRequest = deferred<AgentFsFile>()
    vi.mocked(getAgentFsFile).mockImplementation((path) => {
      return path === scriptPath ? mainRequest.promise : workflowRequest.promise
    })
    render(<FilesTab projectId="project-1" />)

    fireEvent.click(await screen.findByRole("button", { name: "src" }))
    fireEvent.click(await screen.findByRole("button", { name: "main.nf" }))
    fireEvent.click(screen.getByRole("button", { name: "workflow.wdl" }))

    await act(async () => {
      mainRequest.resolve({
        path: scriptPath,
        content: "nextflow content",
        truncated: false,
        size: 16,
        language: "nextflow",
      })
    })
    expect(screen.queryByText("nextflow content")).not.toBeInTheDocument()

    await act(async () => {
      workflowRequest.resolve({
        path: workflowPath,
        content: "workflow content",
        truncated: false,
        size: 16,
        language: "wdl",
      })
    })
    expect(await screen.findByText("workflow content")).toBeInTheDocument()
  })
})
