import { describe, expect, it } from "vitest"

import {
  applyConversationProjectionEvent,
  createConversationProjection,
} from "@/lib/agent/projection/conversation-projection"

import {
  emptySnapshotFixture,
  entryFixture,
  runFixture,
} from "../fixtures/presentation-contract"

function initialProjection() {
  const result = createConversationProjection(emptySnapshotFixture)
  if (!result.ok) throw new Error(result.diagnostic.message)
  return result
}

describe("Conversation event reconciliation", () => {
  it("applies a current event once and ignores its duplicate revision", () => {
    const initial = initialProjection()
    const event = { type: "run.updated", run: runFixture() }

    const applied = applyConversationProjectionEvent(initial.state, event)
    const duplicate = applyConversationProjectionEvent(applied.state, event)

    expect(applied.outcome).toBe("applied")
    expect(applied.view.activeWork?.runId).toBe("run-1")
    expect(duplicate.outcome).toBe("ignored")
    expect(duplicate.view).toEqual(applied.view)
  })

  it("requests a fresh snapshot for an out-of-order committed entry", () => {
    const initial = initialProjection()
    const result = applyConversationProjectionEvent(initial.state, {
      type: "entry.committed",
      entry: entryFixture({
        id: "entry-2",
        sequence: 2,
        type: "message",
        payload: {
          role: "assistant",
          parts: [{ id: "text-2", type: "text", text: "Too early" }],
        },
      }),
    })

    expect(result.outcome).toBe("needs_snapshot")
    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "unknown",
        diagnosticCode: "event_gap",
      }),
    ])
  })

  it("turns an unknown event into a diagnostic block while preserving the view", () => {
    const initial = initialProjection()
    const result = applyConversationProjectionEvent(initial.state, {
      type: "provider.cache.invalidated",
      private_state: "not-for-ui",
    })

    expect(result.outcome).toBe("diagnostic")
    expect(result.view.transcript).toEqual([
      expect.objectContaining({
        type: "unknown",
        originalType: "provider.cache.invalidated",
        diagnosticCode: "unknown_event_type",
      }),
    ])
  })
})
