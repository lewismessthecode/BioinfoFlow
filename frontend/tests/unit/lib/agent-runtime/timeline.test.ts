import { describe, expect, it } from "vitest"

import { buildAgentRuntimeTimeline } from "@/lib/agent-runtime"
import type { AgentRuntimeEvent, AgentRuntimeTurn } from "@/lib/agent-runtime"

const turn: AgentRuntimeTurn = {
  id: "turn-1",
  session_id: "session-1",
  workspace_id: "workspace-1",
  user_id: "user-1",
  input_text: "Start",
  status: "running",
  iteration_count: 1,
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
}

function event(
  id: string,
  seq: number,
  type: string,
  payload: Record<string, unknown>,
): AgentRuntimeEvent {
  return {
    id,
    session_id: "session-1",
    turn_id: "turn-1",
    seq,
    type,
    payload,
    visibility: "user",
    schema_version: 1,
    created_at: `2026-07-24T00:00:0${seq}Z`,
    updated_at: `2026-07-24T00:00:0${seq}Z`,
  }
}

describe("active turn steering timeline", () => {
  it("merges received and delivered steer events into one user segment", () => {
    const [entry] = buildAgentRuntimeTimeline(
      [turn],
      [
        event("received", 2, "turn.steer.received", {
          steer_id: "steer-1",
          input_text: "Use uv.",
          delivery: "pending",
        }),
        event("delivered", 4, "turn.steer.delivered", {
          steer_id: "steer-1",
          input_text: "Use uv.",
          delivery: "delivered",
        }),
      ],
    )

    expect(entry.segments).toContainEqual(
      expect.objectContaining({
        kind: "user_steer",
        seqStart: 2,
        seqEnd: 4,
        steer: expect.objectContaining({
          id: "steer-1",
          text: "Use uv.",
          status: "delivered",
        }),
      }),
    )
  })

  it("keeps received-only and cancelled steering states visible", () => {
    const [entry] = buildAgentRuntimeTimeline(
      [turn],
      [
        event("pending", 2, "turn.steer.received", {
          steer_id: "steer-pending",
          input_text: "Keep checking.",
        }),
        event("received-cancelled", 3, "turn.steer.received", {
          steer_id: "steer-cancelled",
          input_text: "Use the other file.",
        }),
        event("cancelled", 5, "turn.steer.cancelled", {
          steer_id: "steer-cancelled",
          input_text: "Use the other file.",
        }),
      ],
    )

    const steers = entry.segments.filter((segment) => segment.kind === "user_steer")
    expect(steers).toEqual([
      expect.objectContaining({ steer: expect.objectContaining({ status: "pending" }) }),
      expect.objectContaining({ steer: expect.objectContaining({ status: "cancelled" }) }),
    ])
  })

  it("groups events by turn without rescanning every event for every turn", () => {
    let turnIdReads = 0
    const turns = Array.from({ length: 40 }, (_, index) => ({
      ...turn,
      id: `turn-${index}`,
    }))
    const events = Array.from({ length: 400 }, (_, index) => {
      const item = event(`event-${index}`, index + 1, "turn.started", {})
      const turnId = `turn-${index % turns.length}`
      return Object.defineProperty(item, "turn_id", {
        configurable: true,
        enumerable: true,
        get() {
          turnIdReads += 1
          return turnId
        },
      })
    })

    buildAgentRuntimeTimeline(turns, events)

    expect(turnIdReads).toBeLessThan(events.length * 4)
  })
})
