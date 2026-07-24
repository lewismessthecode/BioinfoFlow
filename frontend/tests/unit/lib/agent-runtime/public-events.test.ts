import { describe, expect, it } from "vitest"

import { normalizePublicAgentEvent } from "@/lib/agent-runtime/public-events"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime/types"

const baseEvent: Omit<AgentRuntimeEvent, "type" | "payload"> = {
  id: "event-1",
  session_id: "session-1",
  turn_id: "turn-1",
  seq: 1,
  visibility: "user",
  schema_version: 1,
  created_at: "2026-07-24T00:00:00Z",
  updated_at: "2026-07-24T00:00:00Z",
}

function publicEvent(type: string, payload: Record<string, unknown>): AgentRuntimeEvent {
  return { ...baseEvent, type, payload }
}

describe("normalizePublicAgentEvent", () => {
  it.each([
    ["turn.lifecycle", { status: "recovery_enqueued" }, "turn.recovery.enqueued"],
    ["turn.steering", { status: "delivered" }, "turn.steer.delivered"],
    ["model.lifecycle", { status: "fallback" }, "model.fallback"],
    [
      "assistant.content",
      { kind: "thinking", phase: "summary", content: "checked" },
      "assistant.thinking.summary",
    ],
    ["assistant.tool_call", { phase: "completed" }, "assistant.tool_call.completed"],
    ["action.lifecycle", { status: "waiting_decision" }, "action.waiting_decision"],
    ["artifact.created", { artifact_id: "artifact-1" }, "artifact.created"],
    ["memory.lifecycle", { status: "proposed" }, "memory.proposed"],
  ])("normalizes %s into the existing reducer event", (type, payload, expected) => {
    expect(normalizePublicAgentEvent(publicEvent(type, payload))?.type).toBe(expected)
  })

  it("rejects malformed discriminators and unknown public event categories", () => {
    expect(
      normalizePublicAgentEvent(publicEvent("assistant.content", { kind: "text" })),
    ).toBeNull()
    expect(normalizePublicAgentEvent(publicEvent("agent.everything", {}))).toBeNull()
  })
})
