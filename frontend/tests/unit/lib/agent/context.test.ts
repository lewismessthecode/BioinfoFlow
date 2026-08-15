import { beforeEach, describe, expect, it, vi } from "vitest"

import type { AgentCommand } from "@/lib/agent/contracts"
import {
  agentAttachmentPreviewUrl,
  deleteAgentAttachment,
  searchAgentContext,
  uploadAgentAttachments,
} from "@/lib/agent/context"

const { apiRequestMock, buildApiUrlMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
  buildApiUrlMock: vi.fn(() => "http://test/attachment-preview"),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: apiRequestMock,
  buildApiUrl: buildApiUrlMock,
}))

describe("agent context client", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    buildApiUrlMock.mockClear()
  })

  it("keeps a searched input part unchanged when it is added to a message", async () => {
    const attachmentInputPart = {
      type: "file_ref" as const,
      attachment_id: "attachment-1",
    }
    const workflowInputPart = {
      type: "workflow_ref" as const,
      workflow_id: "workflow-1",
      scope: "project" as const,
      project_id: "project-1",
    }
    apiRequestMock.mockResolvedValueOnce({
      data: {
        results: [
          {
            id: "attachment:attachment-1",
            kind: "file",
            label: "counts.csv",
            detail: "Uploaded attachment",
            input_part: attachmentInputPart,
          },
          {
            id: "workflow:workflow-1",
            kind: "workflow",
            label: "RNA-seq",
            detail: "1.2.0 · nextflow",
            input_part: workflowInputPart,
          },
        ],
        counts: { file: 1, workflow: 1, run: 0 },
        next_cursor: null,
      },
    })

    const result = await searchAgentContext({
      query: "rna",
      scope: "mixed",
      projectId: "project-1",
      sessionId: "session-1",
    })
    const command: AgentCommand = {
      type: "message",
      command_id: "command-1",
      parts: result.results.map((item) => item.input_part),
    }

    expect(command.parts[0]).toBe(attachmentInputPart)
    expect(command.parts[1]).toBe(workflowInputPart)
    expect(apiRequestMock).toHaveBeenCalledWith("/agent/context/search", {
      params: {
        q: "rna",
        scope: "mixed",
        project_id: "project-1",
        session_id: "session-1",
      },
      signal: undefined,
    })
  })

  it("reduces uploaded attachment records to durable attachment references", async () => {
    apiRequestMock.mockResolvedValueOnce({
      data: [
        {
          id: "attachment-1",
          filename: "sample.csv",
          kind: "file",
          size_bytes: 42,
          status: "ready",
        },
      ],
    })
    const file = new File(["sample"], "sample.csv", { type: "text/csv" })

    const parts = await uploadAgentAttachments({
      sessionId: "session-1",
      kind: "file",
      files: [file],
    })

    const [path, options] = apiRequestMock.mock.calls[0]
    expect(path).toBe("/agent/sessions/session-1/attachments")
    expect(options.method).toBe("POST")
    expect(options.body).toBeInstanceOf(FormData)
    expect((options.body as FormData).get("kind")).toBe("file")
    expect((options.body as FormData).get("source")).toBe("upload")
    expect((options.body as FormData).getAll("files")).toEqual([file])
    expect(parts).toEqual([
      { type: "attachment_ref", attachment_id: "attachment-1" },
    ])
  })

  it("supports folder paths plus preview and deletion without the old runtime", async () => {
    apiRequestMock.mockResolvedValueOnce({ data: [] })
    const first = new File(["a"], "a.txt", { type: "text/plain" })
    const second = new File(["b"], "b.txt", { type: "text/plain" })

    await uploadAgentAttachments({
      sessionId: "session-1",
      kind: "folder",
      files: [first, second],
      relativePaths: ["reads/a.txt", "reads/nested/b.txt"],
    })
    await deleteAgentAttachment("attachment-1")

    const uploadBody = apiRequestMock.mock.calls[0][1].body as FormData
    expect(uploadBody.getAll("relative_paths")).toEqual([
      "reads/a.txt",
      "reads/nested/b.txt",
    ])
    expect(agentAttachmentPreviewUrl("attachment-1")).toBe(
      "http://test/attachment-preview",
    )
    expect(buildApiUrlMock).toHaveBeenCalledWith(
      "/agent/attachments/attachment-1/preview",
    )
    expect(apiRequestMock).toHaveBeenLastCalledWith(
      "/agent/attachments/attachment-1",
      { method: "DELETE" },
    )
  })
})
