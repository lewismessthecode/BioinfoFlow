import { describe, expect, it } from "vitest"

import { decodeAgentEvent, decodeAgentSnapshot } from "@/lib/agent/protocol"

function validSnapshot() {
  return {
    protocol_version: 1,
    session: {
      id: "session-1",
      user_id: "user-1",
      workspace_id: "workspace-1",
      project_id: null,
      title: null,
      model: {
        provider: "openai",
        model: "gpt-test",
        display_name: "GPT Test",
        supports_vision: false,
        supports_reasoning: true,
        supports_tools: true,
      },
      permission_mode: "ask_dangerous",
      workspace_access: "read_write",
      status: "active",
      created_at: "2026-08-16T00:00:00Z",
      updated_at: "2026-08-16T00:00:00Z",
    },
    runs: [],
    entries: [],
    active_run: null,
  }
}

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
  it("accepts a complete versioned snapshot", () => {
    const snapshot = validSnapshot()
    expect(decodeAgentSnapshot(snapshot)).toEqual({ ok: true, value: snapshot })
  })

  it("rejects snapshots without a protocol version", () => {
    const snapshot = validSnapshot()
    Reflect.deleteProperty(snapshot, "protocol_version")
    expect(decodeAgentSnapshot(snapshot)).toEqual({
      ok: false,
      reason: "malformed",
    })
  })

  it("rejects unsupported snapshot protocol majors", () => {
    expect(
      decodeAgentSnapshot({ ...validSnapshot(), protocol_version: 2 }),
    ).toEqual({ ok: false, reason: "unsupported_version" })
  })

  it("rejects snapshots with an invalid nested active run", () => {
    expect(
      decodeAgentSnapshot({
        ...validSnapshot(),
        active_run: {},
      }),
    ).toEqual({ ok: false, reason: "malformed" })
  })

  it("rejects nested tool updates that cannot enter the canonical store", () => {
    expect(
      decodeAgentEvent({
        type: "tool.updated",
        protocol_version: 1,
        run_id: "run-1",
        tool: { call_id: "call-1" },
      }),
    ).toEqual({ ok: false, reason: "malformed" })
  })

  it("rejects committed entries with malformed message parts", () => {
    expect(
      decodeAgentEvent({
        type: "entry.committed",
        protocol_version: 1,
        entry: {
          id: "entry-1",
          session_id: "session-1",
          run_id: null,
          sequence: 1,
          schema_version: 1,
          created_at: "2026-08-16T00:00:00Z",
          type: "message",
          payload: { role: "assistant", parts: [{ type: "text" }] },
        },
      }),
    ).toEqual({ ok: false, reason: "malformed" })
  })
})
