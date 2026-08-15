import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createAgentSession,
  dispatchAgentCommand,
  fetchAgentArtifactContent,
  getAgentArtifact,
  getAgentSnapshot,
  listAgentSessions,
  updateAgentSession,
} from "@/lib/agent/client"
import type { SessionSnapshot } from "@/lib/agent/contracts"
import { apiRequest, buildApiUrl } from "@/lib/api"

vi.mock("@/lib/api", () => ({
  apiRequest: vi.fn(),
  buildApiUrl: vi.fn(),
}))

const mockedApiRequest = vi.mocked(apiRequest)
const mockedBuildApiUrl = vi.mocked(buildApiUrl)

describe("agent client", () => {
  beforeEach(() => {
    mockedApiRequest.mockReset()
    mockedBuildApiUrl.mockReset()
    vi.unstubAllGlobals()
  })

  it("loads public artifact details without exposing storage paths in its contract", async () => {
    const artifact = {
      id: "artifact-1",
      session_id: "session-1",
      run_id: "run-1",
      type: "report",
      title: "qc-report.html",
      summary: "Quality-control report",
      payload: { sections: 4 },
      resource_ref: {
        kind: "stored_file",
        filename: "qc-report.html",
        mime_type: "text/html",
        size_bytes: 2048,
      },
      created_at: "2026-08-15T08:00:00Z",
      updated_at: "2026-08-15T08:00:01Z",
    }
    mockedApiRequest.mockResolvedValueOnce({ data: artifact })

    await expect(getAgentArtifact("artifact-1")).resolves.toBe(artifact)
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/agent/artifacts/artifact-1",
      undefined,
    )
  })

  it("fetches authenticated artifact bytes and preserves the server filename", async () => {
    mockedBuildApiUrl.mockReturnValue(
      "http://localhost:8000/api/v1/agent/artifacts/artifact-1/download",
    )
    const response = new Response("report body", {
      headers: {
        "content-disposition": "attachment; filename*=UTF-8''qc-report.txt",
        "content-type": "text/plain; charset=utf-8",
      },
    })
    const fetchMock = vi.fn().mockResolvedValue(response)
    vi.stubGlobal("fetch", fetchMock)

    const content = await fetchAgentArtifactContent("artifact-1")

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/agent/artifacts/artifact-1/download",
      { credentials: "include", signal: undefined },
    )
    expect(content.filename).toBe("qc-report.txt")
    expect(content.mediaType).toBe("text/plain")
    await expect(content.blob.text()).resolves.toBe("report body")
  })

  it("creates a session and returns its authoritative snapshot", async () => {
    const snapshot = { session: { id: "session-1" } } as SessionSnapshot
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })

    await expect(
      createAgentSession({
        projectId: "project-1",
        permissionMode: "ask_dangerous",
        workspaceAccess: "read_write",
        modelId: "model-1",
      }),
    ).resolves.toBe(snapshot)
    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/sessions", {
      method: "POST",
      body: JSON.stringify({
        project_id: "project-1",
        title: undefined,
        permission_mode: "ask_dangerous",
        workspace_access: "read_write",
        model_id: "model-1",
      }),
    })
  })

  it("loads summaries and the explicit snapshot endpoint", async () => {
    const summaries = [{ id: "session-1" }]
    const snapshot = { session: { id: "session-1" } } as SessionSnapshot
    mockedApiRequest
      .mockResolvedValueOnce({ data: summaries })
      .mockResolvedValueOnce({ data: snapshot })

    await expect(listAgentSessions({ includeArchived: true })).resolves.toBe(
      summaries,
    )
    await expect(getAgentSnapshot("session-1")).resolves.toBe(snapshot)

    expect(mockedApiRequest).toHaveBeenNthCalledWith(1, "/agent/sessions", {
      params: { include_archived: true },
    })
    expect(mockedApiRequest).toHaveBeenNthCalledWith(
      2,
      "/agent/sessions/session-1/snapshot",
    )
  })

  it("sends one of the four public commands without choosing prompt or follow-up", async () => {
    const snapshot = { session: { id: "session-1" } } as SessionSnapshot
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })
    const command = {
      type: "message" as const,
      command_id: "command-1",
      parts: [{ type: "text" as const, text: "Inspect this" }],
    }

    await expect(dispatchAgentCommand("session-1", command)).resolves.toBe(
      snapshot,
    )
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/agent/sessions/session-1/commands",
      { method: "POST", body: JSON.stringify(command) },
    )
  })

  it("preserves the exact public context-reference command shapes", async () => {
    const snapshot = { session: { id: "session-1" } } as SessionSnapshot
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })
    const command = {
      type: "message" as const,
      command_id: "command-context",
      parts: [
        { type: "attachment_ref" as const, attachment_id: "attachment-1" },
        { type: "file_ref" as const, attachment_id: "attachment-2" },
        {
          type: "directory_ref" as const,
          project_id: "project-1",
          path: "results/",
        },
        {
          type: "workflow_ref" as const,
          workflow_id: "workflow-1",
          scope: "global" as const,
        },
        {
          type: "workflow_ref" as const,
          workflow_id: "workflow-2",
          scope: "project" as const,
          project_id: "project-1",
        },
        { type: "run_ref" as const, run_id: "run-1" },
      ],
    }

    await expect(dispatchAgentCommand("session-1", command)).resolves.toBe(
      snapshot,
    )
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/agent/sessions/session-1/commands",
      { method: "POST", body: JSON.stringify(command) },
    )
  })

  it("patches only editable session metadata", async () => {
    const snapshot = { session: { id: "session-1" } } as SessionSnapshot
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })

    await expect(
      updateAgentSession("session-1", {
        title: "RNA-seq review",
        permissionMode: "full_access",
        workspaceAccess: "read_only",
        status: "archived",
      }),
    ).resolves.toBe(snapshot)
    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/sessions/session-1", {
      method: "PATCH",
      body: JSON.stringify({
        title: "RNA-seq review",
        permission_mode: "full_access",
        workspace_access: "read_only",
        status: "archived",
      }),
    })
  })
})
