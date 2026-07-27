import { describe, expect, it } from "vitest"

import { reduceAgentTree } from "@/lib/agent-runtime/agent-tree"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime/types"

describe("reduceAgentTree", () => {
  it("reduces lifecycle events by child session and sorts canonical task paths", () => {
    const tree = reduceAgentTree([
      lifecycle(1, "child-b", "/root/zeta", "running"),
      lifecycle(2, "child-a", "/root/alpha", "running", {
        effective_model: "cheap-model",
      }),
      lifecycle(3, "child-a", "/root/alpha", "completed", {
        final_text: "README found",
      }),
    ])

    expect(tree.map((agent) => agent.taskPath)).toEqual(["/root/alpha", "/root/zeta"])
    expect(tree[0]).toMatchObject({
      childSessionId: "child-a",
      status: "completed",
      effectiveModel: "cheap-model",
      finalText: "README found",
      sequence: 3,
    })
  })

  it("ignores stale lifecycle events for the same child", () => {
    const tree = reduceAgentTree([
      lifecycle(9, "child-a", "/root/reader", "completed"),
      lifecycle(4, "child-a", "/root/reader", "running"),
    ])

    expect(tree[0]).toMatchObject({ status: "completed", sequence: 9 })
  })

  it("keeps a terminal status monotonic for later events from the same turn", () => {
    const tree = reduceAgentTree([
      lifecycle(8, "child-a", "/root/reader", "completed", {
        child_turn_id: "turn-1",
        final_text: "README found",
      }),
      lifecycle(9, "child-a", "/root/reader", "running", {
        child_turn_id: "turn-1",
      }),
    ])

    expect(tree[0]).toMatchObject({
      childTurnId: "turn-1",
      status: "completed",
      finalText: "README found",
      sequence: 9,
    })
  })

  it("clears terminal fields when a follow-up starts a new child turn", () => {
    const tree = reduceAgentTree([
      lifecycle(4, "child-a", "/root/reader", "errored", {
        child_turn_id: "turn-1",
        final_text: "old summary",
        error_code: "model_request_failed",
        error_message: "Model provider authentication failed.",
        termination_reason: "model_failed",
        token_usage: { total_tokens: 42 },
      }),
      lifecycle(5, "child-a", "/root/reader", "", {
        activity: "followup",
        child_turn_id: "turn-2",
      }),
    ])

    expect(tree[0]).toEqual(
      expect.objectContaining({
        childTurnId: "turn-2",
        status: "pending_init",
        sequence: 5,
      }),
    )
    expect(tree[0].finalText).toBeUndefined()
    expect(tree[0].errorCode).toBeUndefined()
    expect(tree[0].errorMessage).toBeUndefined()
    expect(tree[0].terminationReason).toBeUndefined()
    expect(tree[0].tokenUsage).toBeUndefined()
  })
})

function lifecycle(
  seq: number,
  childSessionId: string,
  taskName: string,
  status: string,
  payload: Record<string, unknown> = {},
): AgentRuntimeEvent {
  return {
    id: `event-${seq}`,
    session_id: "root-session",
    turn_id: "root-turn",
    seq,
    type: "agent.lifecycle",
    payload: {
      activity: status,
      child_session_id: childSessionId,
      task_name: taskName,
      status,
      ...payload,
    },
    visibility: "user",
    schema_version: 1,
    created_at: `2026-07-27T00:00:0${seq}Z`,
    updated_at: `2026-07-27T00:00:0${seq}Z`,
  }
}
