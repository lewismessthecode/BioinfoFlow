import { describe, expect, it } from "vitest"

import { decodeAgentEvent, decodeAgentSnapshot } from "@/lib/agent/protocol"

describe("decodeAgentEvent", () => {
  it("accepts a versioned event with the expected discriminator and ids", () => {
    expect(
      decodeAgentEvent({
        type: "assistant.delta",
        protocol_version: 1,
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "part-1",
        part_type: "text",
        start_offset: 0,
        end_offset: 2,
        delta: "Hi",
      }),
    ).toEqual({
      ok: true,
      value: expect.objectContaining({
        type: "assistant.delta",
        run_id: "run-1",
      }),
    })
  })

  it("rejects unsupported protocol majors with a recoverable reason", () => {
    expect(
      decodeAgentEvent({
        type: "assistant.delta",
        protocol_version: 2,
        run_id: "run-1",
      }),
    ).toEqual({ ok: false, reason: "unsupported_version" })
  })

  it("rejects malformed known events instead of trusting a type assertion", () => {
    expect(
      decodeAgentEvent({
        type: "tool.updated",
        protocol_version: 1,
        run_id: "run-1",
      }),
    ).toEqual({ ok: false, reason: "malformed" })
  })
})

describe("decodeAgentSnapshot", () => {
  it("accepts legacy snapshots that omit the optional active run", () => {
    expect(
      decodeAgentSnapshot({ session: { id: "session-1" }, runs: [], entries: [] }),
    ).toEqual({
      ok: true,
      value: { session: { id: "session-1" }, runs: [], entries: [] },
    })
  })

  it("rejects snapshots with an invalid active run", () => {
    expect(
      decodeAgentSnapshot({
        session: { id: "session-1" },
        runs: [],
        entries: [],
        active_run: "run-1",
      }),
    ).toEqual({ ok: false, reason: "malformed" })
  })
})
