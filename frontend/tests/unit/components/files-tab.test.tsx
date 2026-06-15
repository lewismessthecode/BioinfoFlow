import { render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { FilesTab } from "@/components/bioinfoflow/agent-runtime/files-tab"
import { getAgentFsTree } from "@/lib/agent-runtime"

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
    vi.mocked(getAgentFsTree).mockResolvedValue({
      path: "/data/projects/project-1",
      entries: [{ name: "workflow.wdl", path: "/data/projects/project-1/workflow.wdl", type: "file" }],
    })
  })

  it("loads the project root when opened with a project id", async () => {
    render(<FilesTab projectId="project-1" />)

    await waitFor(() => {
      expect(getAgentFsTree).toHaveBeenCalledWith(null, "project-1")
    })
    expect(await screen.findByText("workflow.wdl")).toBeInTheDocument()
  })
})
