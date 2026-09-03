import { beforeEach, describe, expect, it, vi } from "vitest"

const mocks = vi.hoisted(() => ({
  apiRequest: vi.fn(),
  buildApiUrl: vi.fn(),
  listAgentArtifacts: vi.fn(),
  fetchAgentArtifactContent: vi.fn(),
}))

vi.mock("@/lib/api", () => ({
  apiRequest: mocks.apiRequest,
  buildApiUrl: mocks.buildApiUrl,
}))

vi.mock("@/lib/agent/client", () => ({
  listAgentArtifacts: mocks.listAgentArtifacts,
  fetchAgentArtifactContent: mocks.fetchAgentArtifactContent,
}))

import { bioinfoFlowAgentWorkspaceAdapter } from "@/lib/agent/workspace-adapter"

describe("bioinfoFlowAgentWorkspaceAdapter", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    mocks.apiRequest.mockReset()
    mocks.buildApiUrl.mockReset()
    mocks.listAgentArtifacts.mockReset()
    mocks.fetchAgentArtifactContent.mockReset()
  })

  it("lists only server-owned session artifacts without scanning project files", async () => {
    mocks.listAgentArtifacts.mockResolvedValueOnce([
      {
        id: "artifact-1",
        session_id: "session-1",
        run_id: "run-1",
        type: "report",
        title: "report.json",
        summary: "QC report",
        payload: null,
        resource_ref: {
          kind: "stored_file",
          filename: "report.json",
          mime_type: "application/json",
          size_bytes: 12,
          sha256: "abc",
        },
        created_at: "2026-08-17T00:00:00Z",
        updated_at: "2026-08-17T00:00:00Z",
      },
    ])
    const artifacts = await bioinfoFlowAgentWorkspaceAdapter.listArtifacts({
      sessionId: "session-1",
      projectId: "project-1",
    })

    expect(mocks.listAgentArtifacts).toHaveBeenCalledWith("session-1", {
      signal: undefined,
    })
    expect(mocks.apiRequest).not.toHaveBeenCalled()
    expect(artifacts).toEqual([
      expect.objectContaining({
        id: "session:artifact-1",
        source: "session",
        runId: "run-1",
        title: "report.json",
        mediaType: "application/json",
      }),
    ])
  })

  it("returns no artifacts when a session is unavailable", async () => {
    const artifacts = await bioinfoFlowAgentWorkspaceAdapter.listArtifacts({
      projectId: "project-1",
    })

    expect(artifacts).toEqual([])
    expect(mocks.listAgentArtifacts).not.toHaveBeenCalled()
    expect(mocks.apiRequest).not.toHaveBeenCalled()
  })

  it("keeps the inferred HTML media type when file downloads are octet streams", async () => {
    mocks.buildApiUrl.mockReturnValueOnce("http://localhost/files/index.html")
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response("<h1>BioinfoFlow</h1>", {
          headers: { "content-type": "application/octet-stream" },
        }),
      ),
    )

    const content = await bioinfoFlowAgentWorkspaceAdapter.fetchArtifactContent({
      artifact: {
        id: "workspace:project-1:index.html",
        source: "workspace",
        title: "index.html",
        summary: null,
        kind: "html",
        mediaType: "text/html",
        sizeBytes: 22,
        createdAt: "2026-08-17T01:00:00Z",
        updatedAt: "2026-08-17T01:00:00Z",
        payload: null,
        resource: { kind: "workspace", projectId: "project-1", path: "index.html" },
      },
    })

    expect(content.mediaType).toBe("text/html")
    expect(content.blob.type).toBe("text/html")
    expect(await content.blob.text()).toContain("BioinfoFlow")
  })
})
