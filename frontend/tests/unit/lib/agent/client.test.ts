import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createAgentSession,
  dispatchAgentCommand,
  fetchAgentArtifactContent,
  getAgentArtifact,
  getAgentSnapshot,
  listAgentArtifacts,
  listAgentSessions,
  updateAgentSession,
} from "@/lib/agent/client"
import { apiRequest, buildApiUrl } from "@/lib/api"

import { emptySnapshotFixture } from "./fixtures/presentation-contract"

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

  it("lists artifacts through the public session endpoint", async () => {
    const artifacts = [{ id: "artifact-1" }]
    mockedApiRequest.mockResolvedValueOnce({ data: artifacts })

    await expect(listAgentArtifacts("session-1")).resolves.toBe(artifacts)
    expect(mockedApiRequest).toHaveBeenCalledWith(
      "/agent/sessions/session-1/artifacts",
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
    const snapshot = emptySnapshotFixture
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })

    await expect(
      createAgentSession({
        projectId: "project-1",
        permissionMode: "ask_dangerous",
        workspaceAccess: "read_write",
        modelId: "model-1",
        environmentScope: {
          mode: "manual",
          selected_environment_ids: ["local", "gpu-01"],
        },
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
        provider: undefined,
        model: undefined,
        environment_scope: {
          mode: "manual",
          selected_environment_ids: ["local", "gpu-01"],
        },
      }),
    })
  })

  it("creates a session from a provider and model when no catalog id exists", async () => {
    const snapshot = emptySnapshotFixture
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })

    await createAgentSession({
      provider: "openai-compatible",
      model: "local-model",
    })

    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/sessions", {
      method: "POST",
      body: JSON.stringify({
        project_id: null,
        title: undefined,
        permission_mode: undefined,
        workspace_access: undefined,
        model_id: undefined,
        provider: "openai-compatible",
        model: "local-model",
        environment_scope: undefined,
      }),
    })
  })

  it("loads summaries and the explicit snapshot endpoint", async () => {
    const summaries = [{ id: "session-1" }]
    const snapshot = emptySnapshotFixture
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

  it("rejects a malformed snapshot response at the HTTP boundary", async () => {
    mockedApiRequest.mockResolvedValueOnce({
      data: { session: { id: "session-1" } },
    })

    await expect(getAgentSnapshot("session-1")).rejects.toMatchObject({
      name: "PresentationContractError",
      diagnostic: {
        code: "invalid_payload",
        originalType: "snapshot",
      },
    })
  })

  it("validates snapshots returned by every session mutation endpoint", async () => {
    const malformed = { session: { id: "session-1" } }
    const mutations = [
      () => createAgentSession({ projectId: "project-1" }),
      () => updateAgentSession("session-1", { title: "Analysis" }),
      () =>
        dispatchAgentCommand("session-1", {
          type: "message",
          command_id: "command-1",
          parts: [{ type: "text", text: "Inspect this" }],
        }),
    ]

    for (const mutate of mutations) {
      mockedApiRequest.mockResolvedValueOnce({ data: malformed })
      await expect(mutate()).rejects.toMatchObject({
        name: "PresentationContractError",
        diagnostic: {
          code: "invalid_payload",
          originalType: "snapshot",
        },
      })
    }
  })

  it("sends one of the four public commands without choosing prompt or follow-up", async () => {
    const snapshot = emptySnapshotFixture
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
    const snapshot = emptySnapshotFixture
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
    const snapshot = emptySnapshotFixture
    mockedApiRequest.mockResolvedValueOnce({ data: snapshot })

    await expect(
      updateAgentSession("session-1", {
        title: "RNA-seq review",
        permissionMode: "full_access",
        workspaceAccess: "read_only",
        model: { provider: "provider-2", model: "claude-sonnet" },
        environmentScope: {
          mode: "manual",
          selected_environment_ids: ["local", "gpu-01"],
        },
        status: "archived",
      }),
    ).resolves.toBe(snapshot)
    expect(mockedApiRequest).toHaveBeenCalledWith("/agent/sessions/session-1", {
      method: "PATCH",
      body: JSON.stringify({
        title: "RNA-seq review",
        permission_mode: "full_access",
        workspace_access: "read_only",
        provider: "provider-2",
        model: "claude-sonnet",
        environment_scope: {
          mode: "manual",
          selected_environment_ids: ["local", "gpu-01"],
        },
        status: "archived",
      }),
    })
  })
})
