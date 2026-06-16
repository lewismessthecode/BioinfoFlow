import { act, fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FilesTab } from "@/components/bioinfoflow/agent-runtime/files-tab"
import { getAgentFsFile, getAgentFsTree, type AgentFsFile, type AgentFsTree } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, number>) => {
    const labels: Record<string, string> = {
      "files.title": "Project files",
      "files.refresh": "Refresh",
      "files.empty": "No files",
      "files.error": "Could not load files",
      "files.up": "Up",
      "files.back": "Back",
      "files.truncated": "File truncated",
      "files.search": "Search loaded files",
      "files.loadedOnly": `${values?.count ?? 0} loaded items`,
      "files.loading": "Loading...",
      "files.addToContext": "Add to context",
      "files.copyPath": "Copy path",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/lib/agent-runtime", () => ({
  getAgentFsTree: vi.fn(),
  getAgentFsFile: vi.fn(),
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
    expect(screen.getByText("src")).toBeInTheDocument()
    expect(screen.getByText("main.nf")).toBeInTheDocument()

    const addButtons = screen.getAllByRole("button", { name: "Add to context" })
    fireEvent.click(addButtons.at(-1)!)
    expect(onAddContext).toHaveBeenCalledWith(scriptPath)
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
