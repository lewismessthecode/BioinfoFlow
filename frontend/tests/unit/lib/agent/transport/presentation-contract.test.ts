import { describe, expect, it } from "vitest"

import {
  parsePresentationEvent,
  parsePresentationSnapshot,
} from "@/lib/agent/transport/presentation-contract"

import { emptySnapshotFixture } from "../fixtures/presentation-contract"

describe("Presentation Contract transport", () => {
  it("normalizes the current unversioned snapshot as protocol version 1", () => {
    expect(parsePresentationSnapshot(emptySnapshotFixture)).toMatchObject({
      ok: true,
      value: {
        protocolVersion: 1,
        snapshot: emptySnapshotFixture,
      },
    })
  })

  it("keeps a structurally known snapshot readable when its version is newer", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        presentation_schema_version: 99,
      }),
    ).toMatchObject({
      ok: true,
      value: {
        protocolVersion: 99,
        snapshot: emptySnapshotFixture,
        diagnostics: [
          {
            code: "unsupported_protocol_version",
            originalType: "snapshot",
            params: { version: "99" },
          },
        ],
      },
    })
  })

  it("preserves an unknown event as a safe diagnostic", () => {
    expect(
      parsePresentationEvent({
        protocol_version: 1,
        type: "harness.checkpoint.rotated",
        checkpoint: { opaque: true },
      }),
    ).toEqual({
      ok: false,
      diagnostic: {
        code: "unknown_event_type",
        message: "Unsupported Agent presentation event: harness.checkpoint.rotated",
        originalType: "harness.checkpoint.rotated",
        params: { originalType: "harness.checkpoint.rotated" },
      },
    })
  })

  it("rejects malformed known events at runtime", () => {
    expect(
      parsePresentationEvent({ type: "run.updated", run: { id: "run-1" } }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "run.updated" },
    })
  })

  it("rejects a malformed known history entry before projection", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "bad-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 1,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "message",
            payload: { role: "assistant" },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })
})
