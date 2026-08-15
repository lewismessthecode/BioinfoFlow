import { screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { AgentContextPicker } from "@/components/bioinfoflow/agent/agent-context-picker"
import { renderWithProviders } from "@/tests/test-utils"

const mocks = vi.hoisted(() => ({
  search: vi.fn(),
  upload: vi.fn(),
}))

vi.mock("@/lib/agent/context", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/agent/context")>()
  return {
    ...actual,
    searchAgentContext: mocks.search,
    uploadAgentAttachments: mocks.upload,
  }
})

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) =>
    ({
      add: "Add context",
      searchPlaceholder: "Search files, workflows, and runs",
      empty: "No matching context",
      uploadFiles: "Upload files",
      uploadFolder: "Upload folder",
      searching: "Searching…",
      uploadError: "Upload failed",
      searchError: "Search failed",
    })[key] ?? key,
}))

describe("AgentContextPicker", () => {
  beforeEach(() => {
    Element.prototype.scrollIntoView = vi.fn()
    vi.stubGlobal(
      "ResizeObserver",
      class ResizeObserver {
        observe() {}
        unobserve() {}
        disconnect() {}
      },
    )
    mocks.search.mockReset()
    mocks.upload.mockReset()
  })

  it("adds the server-provided typed input part without reinterpreting it", async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    mocks.search.mockResolvedValue({
      results: [
        {
          id: "workflow-1",
          kind: "workflow",
          label: "RNA-seq",
          detail: "Project workflow",
          input_part: {
            type: "workflow_ref",
            workflow_id: "workflow-1",
            scope: "project",
            project_id: "project-1",
          },
        },
      ],
      counts: { workflow: 1 },
      next_cursor: null,
    })

    renderWithProviders(
      <AgentContextPicker
        projectId="project-1"
        sessionId="session-1"
        ensureSession={vi.fn().mockResolvedValue("session-1")}
        onAdd={onAdd}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Add context" }))
    await user.type(
      screen.getByPlaceholderText("Search files, workflows, and runs"),
      "rna",
    )

    await user.click(await screen.findByRole("option", { name: /RNA-seq/ }))
    expect(onAdd).toHaveBeenCalledWith({
      id: "workflow-1",
      kind: "workflow",
      label: "RNA-seq",
      detail: "Project workflow",
      input_part: {
        type: "workflow_ref",
        workflow_id: "workflow-1",
        scope: "project",
        project_id: "project-1",
      },
    })
  })

  it("creates a session before uploading draft attachments", async () => {
    const user = userEvent.setup()
    const onAdd = vi.fn()
    const ensureSession = vi.fn().mockResolvedValue("session-new")
    mocks.search.mockResolvedValue({ results: [], counts: {}, next_cursor: null })
    mocks.upload.mockResolvedValue([
      { type: "attachment_ref", attachment_id: "attachment-1" },
    ])

    renderWithProviders(
      <AgentContextPicker
        projectId="project-1"
        sessionId={null}
        ensureSession={ensureSession}
        onAdd={onAdd}
      />,
    )
    await user.click(screen.getByRole("button", { name: "Add context" }))

    const file = new File(["reads"], "reads.fastq", {
      type: "application/octet-stream",
    })
    const input = document.querySelector('input[type="file"]:not([data-folder])')
    expect(input).not.toBeNull()
    await user.upload(input as HTMLInputElement, file)

    await waitFor(() => expect(ensureSession).toHaveBeenCalledTimes(1))
    expect(mocks.upload).toHaveBeenCalledWith({
      sessionId: "session-new",
      kind: "file",
      files: [file],
      source: "upload",
    })
    expect(onAdd).toHaveBeenCalledWith({
      id: "attachment:attachment-1",
      kind: "attachment",
      label: "reads.fastq",
      detail: null,
      input_part: {
        type: "attachment_ref",
        attachment_id: "attachment-1",
      },
    })
  })
})
