import { describe, expect, it } from "vitest"

import {
  parsePresentationEvent,
  parsePresentationSnapshot,
} from "@/lib/agent/transport/presentation-contract"

import {
  activeSnapshotFixture,
  emptySnapshotFixture,
  runFixture,
} from "../fixtures/presentation-contract"

describe("Presentation Contract transport", () => {
  it("normalizes the current unversioned snapshot as protocol version 1", () => {
    const unversionedSnapshot: Record<string, unknown> = {
      ...emptySnapshotFixture,
    }
    delete unversionedSnapshot.presentation_protocol
    delete unversionedSnapshot.presentation_schema_version

    const parsed = parsePresentationSnapshot(unversionedSnapshot)

    expect(parsed).toMatchObject({
      ok: true,
      value: {
        protocolVersion: 1,
        snapshot: {
          ...unversionedSnapshot,
          presentation_protocol: "bioinfoflow.agent.presentation",
          presentation_schema_version: 1,
        },
      },
    })
    if (parsed.ok) expect(parsed.value.snapshot).not.toBe(unversionedSnapshot)
  })

  it("normalizes a legacy event into the canonical versioned DTO", () => {
    const event = { type: "run.updated", run: runFixture() }

    expect(parsePresentationEvent(event)).toEqual({
      ok: true,
      value: {
        protocolVersion: 1,
        event: {
          ...event,
          presentation_protocol: "bioinfoflow.agent.presentation",
          presentation_schema_version: 1,
        },
      },
    })
  })

  it("keeps a structurally known snapshot readable when its version is newer", () => {
    const newerSnapshot = {
      ...emptySnapshotFixture,
      presentation_schema_version: 99,
    }

    expect(
      parsePresentationSnapshot(newerSnapshot),
    ).toMatchObject({
      ok: true,
      value: {
        protocolVersion: 99,
        snapshot: newerSnapshot,
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

    expect(
      parsePresentationEvent({
        type: "run.updated",
        run: { ...runFixture(), status: "teleported" },
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "run.updated" },
    })
  })

  it("accepts the initial queued run revision emitted by the server", () => {
    const queuedRun = runFixture({
      status: "queued",
      phase: null,
      revision: 0,
    })
    const snapshot = {
      ...emptySnapshotFixture,
      runs: [queuedRun],
      active_run: {
        run: queuedRun,
        assistant_draft: null,
        tool_progress: [],
        pending_interaction: null,
      },
    }

    expect(parsePresentationSnapshot(snapshot)).toEqual({
      ok: true,
      value: {
        protocolVersion: 1,
        snapshot,
        diagnostics: [],
      },
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

  it("rejects a reasoning trace without its public provenance", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "reasoning-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "message",
            payload: {
              role: "assistant",
              parts: [
                {
                  id: "reasoning-1",
                  type: "reasoning_trace",
                  text: "Inspect the failing invariant.",
                  provider: "openai",
                },
              ],
            },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("rejects malformed live reasoning-trace metadata", () => {
    expect(
      parsePresentationEvent({
        presentation_protocol: "bioinfoflow.agent.presentation",
        presentation_schema_version: 1,
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "reasoning-1",
        part_type: "reasoning_trace",
        delta: "Inspecting",
        start_offset: 0,
        end_offset: 10,
        provider: 42,
        model: "gpt-5.6",
        source: "reasoning_content",
        truncated: false,
        started_at: "2026-08-16T08:00:00.000Z",
        completed_at: null,
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: {
        code: "invalid_payload",
        originalType: "assistant.delta",
      },
    })

    expect(
      parsePresentationEvent({
        type: "assistant.delta",
        run_id: "run-1",
        draft_id: "draft-1",
        part_id: "reasoning-1",
        part_type: "reasoning_trace",
        delta: "Inspecting",
        start_offset: 0,
        end_offset: 10,
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: {
        code: "invalid_payload",
        originalType: "assistant.delta",
      },
    })
  })

  it("rejects malformed reasoning metadata in an active assistant draft", () => {
    const activeRun = activeSnapshotFixture.active_run
    expect(activeRun).not.toBeNull()
    if (!activeRun) return

    expect(
      parsePresentationSnapshot({
        ...activeSnapshotFixture,
        active_run: {
          ...activeRun,
          assistant_draft: {
            id: "draft-1",
            run_id: "run-1",
            parts: [
              {
                id: "reasoning-1",
                type: "reasoning_trace",
                text: "Inspecting",
                end_offset: 10,
                provider: 42,
                model: "gpt-5.6",
                source: "reasoning_content",
              },
            ],
          },
        },
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })

    expect(
      parsePresentationSnapshot({
        ...activeSnapshotFixture,
        active_run: {
          ...activeRun,
          assistant_draft: {
            id: "draft-1",
            run_id: "run-1",
            parts: [
              {
                id: "reasoning-1",
                type: "reasoning_trace",
                text: "Inspecting",
                end_offset: 10,
              },
            ],
          },
        },
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("preserves public provenance for durable and live reasoning traces", () => {
    const trace = {
      id: "reasoning-1",
      type: "reasoning_trace",
      text: "Inspect the failing invariant.",
      provider: "openai",
      model: "gpt-5.6",
      source: "reasoning_content",
      truncated: true,
      started_at: "2026-08-16T08:00:00.000Z",
      completed_at: "2026-08-16T08:00:02.000Z",
    }
    const snapshot = {
      ...emptySnapshotFixture,
      entries: [
        {
          id: "reasoning-entry",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 2,
          created_at: "2026-08-16T08:00:02.000Z",
          type: "message",
          payload: { role: "assistant", parts: [trace] },
        },
      ],
    }
    const event = {
      presentation_protocol: "bioinfoflow.agent.presentation",
      presentation_schema_version: 1,
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-1",
      part_id: "reasoning-1",
      part_type: "reasoning_trace",
      delta: "Inspect the failing invariant.",
      start_offset: 0,
      end_offset: 30,
      provider: trace.provider,
      model: trace.model,
      source: trace.source,
      truncated: trace.truncated,
      started_at: trace.started_at,
      completed_at: trace.completed_at,
    }

    expect(parsePresentationSnapshot(snapshot)).toEqual({
      ok: true,
      value: {
        protocolVersion: 1,
        snapshot,
        diagnostics: [],
      },
    })
    expect(parsePresentationEvent(event)).toEqual({
      ok: true,
      value: { protocolVersion: 1, event },
    })
  })

  it("rejects a known tool call with an incomplete public shape", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "tool-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "message",
            payload: {
              role: "assistant",
              parts: [
                {
                  id: "tool-1",
                  type: "tool_call",
                  group_id: "group-1",
                  execution_mode: "serial",
                  name: "bash",
                  display_name: "Bash",
                  category: "command",
                  summary: "Inspect the workspace",
                  arguments: {},
                },
              ],
            },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("deep-validates live tool progress before it reaches the store", () => {
    const tool = activeSnapshotFixture.active_run?.tool_progress[0]
    expect(tool).toBeDefined()
    if (!tool) return

    expect(
      parsePresentationEvent({
        type: "tool.updated",
        run_id: "run-1",
        tool: {
          ...tool,
          execution_mode: "harness-private",
          category: "secret",
          status: "teleported",
        },
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "tool.updated" },
    })
  })

  it("rejects a known tool result with malformed output", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "tool-result-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "message",
            payload: {
              role: "tool",
              parts: [
                {
                  id: "tool-result-1",
                  type: "tool_result",
                  call_id: "call-1",
                  status: "completed",
                  summary: "Finished",
                  output: { type: "json" },
                  started_at: null,
                  completed_at: "2026-08-16T08:00:01.000Z",
                  error: null,
                },
              ],
            },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("rejects a known approval request without a complete risk view", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "approval-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "interaction_request",
            payload: {
              interaction_id: "approval-1",
              request: {
                type: "approval",
                call_id: "call-1",
                tool_name: "bash",
                summary: "Run the command",
                input_preview: "bif runs submit workflow.nf",
                allowed_responses: ["approve", "reject"],
                target: {
                  environment_id: "local",
                  display_name: "Local",
                  kind: "local",
                  host: null,
                },
                risk: { level: "act_high" },
              },
            },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("rejects a malformed known interaction response", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "approval-response-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "interaction_response",
            payload: {
              interaction_id: "approval-1",
              response: { type: "approval", approved: "yes" },
            },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })
  })

  it("deep-validates every known non-tool message-part discriminant", () => {
    const invalidParts = [
      { id: "text-1", type: "text" },
      { id: "summary-1", type: "reasoning_summary", text: 1 },
      { id: "attachment-1", type: "attachment_ref", filename: "a.txt", kind: "file", mime_type: null, size_bytes: 1 },
      { id: "file-1", type: "file_ref" },
      { id: "directory-1", type: "directory_ref", label: 1 },
      { id: "workflow-1", type: "workflow_ref", label: "Workflow" },
      { id: "run-ref-1", type: "run_ref", label: "Run" },
      { id: "artifact-1", type: "artifact_ref", title: null, media_type: null },
      { id: "unknown-1", type: "unknown", display_text: "Unsupported" },
    ]

    for (const part of invalidParts) {
      expect(
        parsePresentationSnapshot({
          ...emptySnapshotFixture,
          entries: [
            {
              id: `entry:${part.id}`,
              session_id: "session-1",
              run_id: "run-1",
              sequence: 1,
              schema_version: 2,
              created_at: "2026-08-16T08:00:00.000Z",
              type: "message",
              payload: { role: "assistant", parts: [part] },
            },
          ],
        }),
      ).toMatchObject({
        ok: false,
        diagnostic: { code: "invalid_payload", originalType: "snapshot" },
      })
    }
  })

  it("normalizes future entries and parts into public unknown shapes", () => {
    expect(
      parsePresentationSnapshot({
        ...emptySnapshotFixture,
        entries: [
          {
            id: "unknown-entry",
            session_id: "session-1",
            run_id: "run-1",
            sequence: 1,
            schema_version: 2,
            created_at: "2026-08-16T08:00:00.000Z",
            type: "unknown",
            payload: { display_text: "Unsupported conversation activity" },
          },
        ],
      }),
    ).toMatchObject({
      ok: false,
      diagnostic: { code: "invalid_payload", originalType: "snapshot" },
    })

    const futureContent = parsePresentationSnapshot({
      ...emptySnapshotFixture,
      entries: [
        {
          id: "future-message",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 3,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "message",
          payload: {
            role: "assistant",
            parts: [
              {
                id: "future-part",
                type: "provider_private_state",
                encrypted_content: "opaque-secret",
              },
            ],
          },
        },
      ],
    })
    expect(futureContent).toMatchObject({
      ok: true,
      value: {
        snapshot: {
          entries: [
            {
              type: "message",
              payload: {
                parts: [
                  {
                    id: "future-part",
                    type: "unknown",
                    original_type: "provider_private_state",
                    display_text: "Unsupported conversation content",
                  },
                ],
              },
            },
          ],
        },
      },
    })
    if (futureContent.ok) {
      expect(JSON.stringify(futureContent.value.snapshot)).not.toContain(
        "opaque-secret",
      )
    }

    const futureEntry = parsePresentationSnapshot({
      ...emptySnapshotFixture,
      entries: [
        {
          id: "future-entry",
          session_id: "session-1",
          run_id: "run-1",
          sequence: 1,
          schema_version: 3,
          created_at: "2026-08-16T08:00:00.000Z",
          type: "future_activity",
          payload: { checkpoint: "opaque-secret" },
        },
      ],
    })
    expect(futureEntry).toMatchObject({
      ok: true,
      value: {
        snapshot: {
          entries: [
            {
              id: "future-entry",
              session_id: "session-1",
              run_id: "run-1",
              sequence: 1,
              schema_version: 3,
              created_at: "2026-08-16T08:00:00.000Z",
              type: "unknown",
              payload: {
                original_type: "future_activity",
                display_text: "Unsupported conversation activity",
              },
            },
          ],
        },
      },
    })
    if (futureEntry.ok) {
      expect(JSON.stringify(futureEntry.value.snapshot)).not.toContain(
        "opaque-secret",
      )
    }
  })
})
