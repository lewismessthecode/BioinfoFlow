import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FilesTab } from "@/components/bioinfoflow/agent-runtime/files-tab"
import { getAgentFsFile, getAgentFsTree } from "@/lib/agent-runtime"

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      "files.title": "Project files",
      "files.refresh": "Refresh",
      "files.empty": "No files",
      "files.error": "Could not load files",
      "files.up": "Up",
      "files.back": "Back",
      "files.truncated": "File truncated",
      "files.search": "Search files",
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

describe("FilesTab", () => {
  beforeEach(() => {
    vi.mocked(getAgentFsTree).mockReset()
    vi.mocked(getAgentFsFile).mockReset()
    vi.mocked(getAgentFsTree).mockResolvedValue({
      path: "/data/projects/project-1",
      entries: [{ name: "workflow.wdl", path: "/data/projects/project-1/workflow.wdl", type: "file" }],
    })
    vi.mocked(getAgentFsFile).mockResolvedValue({
      path: "/data/projects/project-1/workflow.wdl",
      content: "workflow content",
      truncated: false,
      size: 16,
      language: "wdl",
    })
  })

  it("loads the project root when opened with a project id", async () => {
    render(<FilesTab projectId="project-1" />)

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(null, "project-1")
    })
    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
  })

  it("searches, previews, and adds files to context", async () => {
    const onAddContext = vi.fn()
    render(<FilesTab projectId="project-1" onAddContext={onAddContext} />)

    fireEvent.change(await screen.findByPlaceholderText("Search files"), {
      target: { value: "workflow" },
    })
    expect(screen.getByText("workflow.wdl")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "workflow.wdl" }))
    await waitFor(() => {
      expect(getAgentFsFile).toHaveBeenCalledWith("/data/projects/project-1/workflow.wdl")
    })
    expect(await screen.findByTestId("agent-file-preview")).toBeInTheDocument()
    expect(screen.getByText("workflow content")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Add to context" }))
    expect(onAddContext).toHaveBeenCalledWith("/data/projects/project-1/workflow.wdl")
  })
})
