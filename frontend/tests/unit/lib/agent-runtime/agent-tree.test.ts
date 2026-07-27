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
