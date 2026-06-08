import { describe, expect, it } from "vitest"

import {
  agentRuntimeReducer,
  initialAgentRuntimeState,
  type AgentRuntimeEvent,
  type AgentRuntimeTurn,
} from "@/lib/agent-runtime"

const event = (id: string, seq: number): AgentRuntimeEvent => ({
  id,
  session_id: "session-1",
  turn_id: "turn-1",
  seq,
  type: "turn.created",
  payload: {},
  visibility: "user",
  schema_version: 1,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
})

const turn = (status: AgentRuntimeTurn["status"]): AgentRuntimeTurn => ({
  id: "turn-1",
  session_id: "session-1",
  project_id: null,
  workspace_id: "workspace-1",
  user_id: "dev",
  input_text: "hello",
  input_parts: null,
  status,
  iteration_count: 0,
  created_at: "2026-06-08T00:00:00Z",
  updated_at: "2026-06-08T00:00:00Z",
})

describe("agentRuntimeReducer", () => {
  it("keeps session events unique and ordered by sequence", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: {
          id: "session-1",
          workspace_id: "workspace-1",
          user_id: "dev",
          role_profile: "bioinformatician",
          permission_mode: "guarded_auto",
          automation_mode: "assisted",
          runtime_mode: "api",
          status: "active",
          created_at: "2026-06-08T00:00:00Z",
          updated_at: "2026-06-08T00:00:00Z",
        },
        turns: [],
        events: [event("event-3", 3), event("event-1", 1), event("event-3", 3)],
      },
    })

    expect(loaded.events.map((item) => item.seq)).toEqual([1, 3])
  })

  it("projects running status from queued or running turns", () => {
    const state = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "turn.upsert",
      turn: turn("running"),
    })

    expect(state.status).toBe("running")

    const idle = agentRuntimeReducer(state, {
      type: "turn.upsert",
      turn: turn("completed"),
    })
    expect(idle.status).toBe("idle")
  })
})
