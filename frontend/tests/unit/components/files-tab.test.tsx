import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FilesTab } from "@/components/bioinfoflow/agent-runtime/files-tab"
import { getAgentFsFile, getAgentFsTree } from "@/lib/agent-runtime"

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

  it("filters only loaded nodes", async () => {
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

    fireEvent.change(screen.getByPlaceholderText("Search loaded files"), {
      target: { value: "main" },
    })
    expect(screen.getByText("main.nf")).toBeInTheDocument()
    expect(screen.queryByText("workflow.wdl")).not.toBeInTheDocument()
  })
})
