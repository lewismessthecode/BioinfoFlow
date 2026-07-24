import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  createAgentRuntimeSession,
  createAgentRuntimeTurn,
  getAgentRuntimeState,
  steerAgentRuntimeTurn,
  updateAgentRuntimeSessionPermissionMode,
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

  it("requests the transcript event view for conversation state", async () => {
    await getAgentRuntimeState("session-1", { eventView: "transcript" })

    expect(apiRequestMock).toHaveBeenCalledWith("/agent/sessions/session-1/state", {
      params: { event_view: "transcript" },
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

  it("posts steering guidance with transcript display metadata", async () => {
    apiRequestMock.mockResolvedValueOnce({
      data: { steer_id: "steer-1", turn_id: "turn-1", delivery: "pending" },
    })

    const outcome = await steerAgentRuntimeTurn("turn-1", {
      inputText: "Use the project virtualenv.",
      inputParts: [{ type: "text", text: "Use the project virtualenv." }],
      activeSkillNames: ["python"],
      metadata: { input_display: { inline_parts: [] } },
    })

    expect(apiRequestMock).toHaveBeenCalledWith("/agent/turns/turn-1/steer", {
      method: "POST",
      body: JSON.stringify({
        input_text: "Use the project virtualenv.",
        input_parts: [{ type: "text", text: "Use the project virtualenv." }],
        active_skill_names: ["python"],
        metadata: { input_display: { inline_parts: [] } },
      }),
    })
    expect(outcome).toEqual({
      kind: "accepted",
      result: { steer_id: "steer-1", turn_id: "turn-1", delivery: "pending" },
    })
  })

  it("serializes auto execution scope when creating a turn", async () => {
    await createAgentRuntimeTurn({
      sessionId: "session-1",
      inputText: "hello",
      executionScope: { mode: "auto" },
    })

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      input_text: "hello",
      execution_scope: {
        mode: "auto",
      },
    })
  })

  it("serializes manual execution scope with local and remote targets", async () => {
    await createAgentRuntimeTurn({
      sessionId: "session-1",
      inputText: "hello",
      executionScope: {
        mode: "manual",
        selected_targets: [
          { kind: "local" },
          { kind: "remote_ssh", connection_id: "connection-1" },
        ],
      },
    })

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      input_text: "hello",
      execution_scope: {
        mode: "manual",
        selected_targets: [
          { kind: "local", type: "local" },
          {
            kind: "remote_ssh",
            type: "remote_ssh",
            connection_id: "connection-1",
            remote_connection_id: "connection-1",
          },
        ],
      },
    })
  })

  it("strips workflow display fields from API input parts while preserving turn metadata", async () => {
    await createAgentRuntimeTurn({
      sessionId: "session-1",
      inputText: "Draft a run plan",
      inputParts: [
        { type: "text", text: "Draft a run plan" },
        {
          kind: "workflow_ref",
          workflow_id: "workflow-rna-12",
          project_id: "project-1",
          scope: "project",
          display_name: "rnaseq-quant-mini",
          display_version: "1.2.0",
        } as never,
      ],
      metadata: {
        input_display: {
          workflow_mentions: [
            {
              workflow_id: "workflow-rna-12",
              project_id: "project-1",
              scope: "project",
              name: "rnaseq-quant-mini",
              version: "1.2.0",
            },
          ],
        },
      },
    } as never)

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body.input_parts).toEqual([
      { type: "text", text: "Draft a run plan" },
      {
        kind: "workflow_ref",
        workflow_id: "workflow-rna-12",
        project_id: "project-1",
        scope: "project",
      },
    ])
    expect(body.metadata).toEqual({
      input_display: {
        workflow_mentions: [
          {
            workflow_id: "workflow-rna-12",
            project_id: "project-1",
            scope: "project",
            name: "rnaseq-quant-mini",
            version: "1.2.0",
          },
        ],
      },
    })
  })

  it("serializes a selected remote execution target when creating a session", async () => {
    await createAgentRuntimeSession({
      title: "Remote session",
      executionTarget: {
        kind: "remote_ssh",
        remote_connection_id: "connection-1",
      },
    })

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      title: "Remote session",
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

  it("serializes a null execution target when clearing session metadata", async () => {
    await updateAgentRuntimeSessionMetadata(
      "session-1",
      { batch: "b001" },
      null,
      { mode: "auto" },
    )

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toMatchObject({
      metadata: { batch: "b001" },
      execution_target: null,
      execution_scope: { mode: "auto" },
    })
  })

  it("serializes pending strategy and returns reconciliation metadata", async () => {
    apiRequestMock.mockResolvedValueOnce({
      data: {
        id: "session-1",
        project_id: null,
        workspace_id: "workspace-1",
        user_id: "dev",
        role_profile: "bioinformatician",
        permission_mode: "bypass",
        automation_mode: "assisted",
        permission_policy_version: 4,
        runtime_mode: "api",
        status: "active",
        pending_strategy: "approve_pending_tools",
        pending_reconciliation: {
          affected_count: 2,
          excluded_count: 1,
          already_resolved_count: 3,
        },
        created_at: "2026-07-13T00:00:00Z",
        updated_at: "2026-07-13T00:00:01Z",
      },
    })

    const updated = await updateAgentRuntimeSessionPermissionMode(
      "session-1",
      "bypass",
      "approve_pending_tools",
    )

    const body = JSON.parse(apiRequestMock.mock.calls[0][1].body)
    expect(body).toEqual({
      permission_mode: "bypass",
      pending_strategy: "approve_pending_tools",
    })
    expect(updated.permission_policy_version).toBe(4)
    expect(updated.pending_strategy).toBe("approve_pending_tools")
    expect(updated.pending_reconciliation).toEqual({
      affected_count: 2,
      excluded_count: 1,
      already_resolved_count: 3,
    })
  })
})
