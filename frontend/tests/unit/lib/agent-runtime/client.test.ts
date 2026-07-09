import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createAgentRuntimeTurn,
  updateAgentRuntimeSessionMetadata,
} from "@/lib/agent-runtime/client"

const apiRequestMock = vi.hoisted(() => vi.fn())

vi.mock("@/lib/api", () => ({
  apiRequest: apiRequestMock,
  buildApiUrl: vi.fn(),
}))

describe("agent runtime client", () => {
  beforeEach(() => {
    apiRequestMock.mockResolvedValue({
      data: {
        id: "turn-1",
        session_id: "session-1",
        project_id: null,
        workspace_id: "workspace-1",
        user_id: "dev",
        input_text: "hello",
        status: "queued",
        iteration_count: 0,
        created_at: "2026-06-08T00:00:00Z",
        updated_at: "2026-06-08T00:00:00Z",
      },
    })
  })

  it("serializes a selected remote execution target when creating a turn", async () => {
    await createAgentRuntimeTurn({
      sessionId: "session-1",
      inputText: "hello",
      executionTarget: {
        kind: "remote_ssh",
        remote_connection_id: "connection-1",
      },
    })

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      input_text: "hello",
      execution_target: {
        kind: "remote_ssh",
        type: "remote_ssh",
        remote_connection_id: "connection-1",
        connection_id: "connection-1",
      },
    })
  })

  it("serializes an explicit local execution target when clearing remote selection", async () => {
    await createAgentRuntimeTurn({
      sessionId: "session-1",
      inputText: "hello",
      executionTarget: { kind: "local" },
    })

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      input_text: "hello",
      execution_target: { kind: "local", type: "local" },
    })
  })

  it("serializes execution target when patching session metadata", async () => {
    await updateAgentRuntimeSessionMetadata(
      "session-1",
      { batch: "b001" },
      { kind: "local" },
    )

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      metadata: { batch: "b001" },
      execution_target: { kind: "local", type: "local" },
    })
  })
})
