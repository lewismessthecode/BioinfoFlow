import { describe, expect, it } from "vitest"

import {
  agentRuntimeReducer,
  initialAgentRuntimeState,
  type AgentRuntimeEvent,
  type AgentRuntimeSession,
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

const turn = (
  status: AgentRuntimeTurn["status"],
  updatedAt = "2026-06-08T00:00:00Z",
): AgentRuntimeTurn => ({
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
  updated_at: updatedAt,
})

const session = (updatedAt = "2026-06-08T00:00:00Z"): AgentRuntimeSession => ({
  id: "session-1",
  workspace_id: "workspace-1",
  user_id: "dev",
  role_profile: "bioinformatician",
  permission_mode: "guarded_auto",
  automation_mode: "assisted",
  runtime_mode: "api",
  status: "active",
  created_at: "2026-06-08T00:00:00Z",
  updated_at: updatedAt,
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

  it("builds a structured assistant timeline from streaming events", () => {
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
        turns: [turn("running")],
        events: [
          {
            ...event("event-1", 1),
            type: "assistant.thinking.delta",
            payload: {
              message_id: "message-1",
              delta: "Inspecting inputs.",
              content: "Inspecting inputs.",
              index: 0,
            },
          },
          {
            ...event("event-2", 2),
            type: "assistant.thinking.completed",
            payload: {
              message_id: "message-1",
              content: "Inspecting inputs.",
              index: 0,
            },
          },
          {
            ...event("event-3", 3),
            type: "assistant.tool_call.started",
            payload: {
              message_id: "message-1",
              call_id: "call-1",
              name: "projects__list",
              status: "building",
              index: 0,
            },
          },
          {
            ...event("event-4", 4),
            type: "assistant.tool_call.delta",
            payload: {
              message_id: "message-1",
              call_id: "call-1",
              name: "projects__list",
              arguments_delta: '{"limit":1}',
              arguments: { limit: 1 },
              status: "building",
              index: 0,
            },
          },
          {
            ...event("event-5", 5),
            type: "assistant.tool_call.completed",
            payload: {
              message_id: "message-1",
              call_id: "call-1",
              name: "projects__list",
              arguments: { limit: 1 },
              status: "completed",
              index: 0,
            },
          },
          {
            ...event("event-6", 6),
            type: "assistant.text.delta",
            payload: {
              message_id: "message-1",
              delta: "Hello ",
              content: "Hello ",
              index: 0,
            },
          },
          {
            ...event("event-7", 7),
            type: "assistant.text.completed",
            payload: {
              message_id: "message-1",
              text: "Hello world",
              content: "Hello world",
              index: 1,
            },
          },
        ],
      },
    })

    expect(loaded.timeline).toHaveLength(1)
    expect(loaded.timeline[0].assistant.messageId).toBe("message-1")
    expect(loaded.timeline[0].assistant.text).toBe("Hello world")
    expect(loaded.timeline[0].assistant.thinking?.content).toBe("Inspecting inputs.")
    expect(loaded.timeline[0].assistant.thinking?.isComplete).toBe(true)
    expect(loaded.timeline[0].assistant.toolCalls).toEqual([
      expect.objectContaining({
        callId: "call-1",
        name: "projects__list",
        status: "completed",
        index: 0,
        arguments: { limit: 1 },
      }),
    ])
    expect(loaded.timeline[0].activityGroups).toEqual([
      expect.objectContaining({
        kind: "read",
        activities: [
          expect.objectContaining({
            callId: "call-1",
            name: "projects__list",
            status: "completed",
          }),
        ],
      }),
    ])
  })

  it("projects rejected action decisions as rejected activity", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("waiting_approval")],
        events: [
          {
            ...event("event-waiting", 1),
            type: "action.waiting_decision",
            payload: {
              action_id: "action-1",
              name: "bash",
              input_preview: "rm build/",
            },
          },
          {
            ...event("event-rejected", 2),
            type: "action.decision_recorded",
            payload: {
              action_id: "action-1",
              name: "bash",
              decision: "reject",
            },
          },
        ],
      },
    })

    expect(loaded.timeline[0].activityGroups[0]).toEqual(
      expect.objectContaining({
        status: "rejected",
        activities: [expect.objectContaining({ status: "rejected" })],
      }),
    )
  })

  it("preserves persisted thinking summaries after later tool calls", () => {
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
        turns: [turn("running")],
        events: [
          {
            ...event("event-thinking", 1),
            type: "assistant.thinking.summary",
            payload: {
              message_id: "message-1",
              content: "I need to inspect the workflow files before answering.",
            },
          },
          {
            ...event("event-tool", 2),
            type: "assistant.tool_call.completed",
            payload: {
              message_id: "message-1",
              call_id: "call-1",
              name: "glob",
              arguments: { pattern: "**/*.wdl" },
              status: "completed",
              index: 0,
            },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.thinking?.content).toBe(
      "I need to inspect the workflow files before answering.",
    )
    expect(loaded.timeline[0].assistant.toolCalls).toHaveLength(1)
  })

  it("accumulates unkeyed thinking stream events into one block", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-thinking-1", 1),
            type: "assistant.thinking.delta",
            payload: { text_delta: "Inspect" },
          },
          {
            ...event("event-thinking-2", 2),
            type: "assistant.thinking.delta",
            payload: { text_delta: " files" },
          },
          {
            ...event("event-thinking-3", 3),
            type: "assistant.thinking.completed",
            payload: { content: "Inspect files" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.thinkingBlocks).toEqual([
      expect.objectContaining({ content: "Inspect files", isComplete: true }),
    ])
  })

  it("marks decisions completed when an action completes without a recorded decision", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("waiting_approval")],
        events: [
          {
            ...event("event-waiting", 1),
            type: "action.waiting_decision",
            payload: { action_id: "action-1", name: "bash" },
          },
          {
            ...event("event-completed", 2),
            type: "action.completed",
            payload: { action_id: "action-1", name: "bash" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments).toContainEqual(
      expect.objectContaining({
        kind: "decision",
        decision: expect.objectContaining({ state: "completed" }),
      }),
    )
  })

  it("marks approved decisions completed when the action completes", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("waiting_approval")],
        events: [
          {
            ...event("event-waiting", 1),
            type: "action.waiting_decision",
            payload: { action_id: "action-1", name: "bash" },
          },
          {
            ...event("event-approved", 2),
            type: "action.decision_recorded",
            payload: { action_id: "action-1", decision: "approve" },
          },
          {
            ...event("event-completed", 3),
            type: "action.completed",
            payload: { action_id: "action-1", name: "bash" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments).toContainEqual(
      expect.objectContaining({
        kind: "decision",
        decision: expect.objectContaining({ state: "completed" }),
      }),
    )
  })

  it("resolves decisions from action events without a matching turn id", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("waiting_approval")],
        events: [
          {
            ...event("event-waiting", 1),
            type: "action.waiting_decision",
            payload: { action_id: "action-1", name: "bash" },
          },
          {
            ...event("event-completed", 2),
            turn_id: null,
            type: "action.completed",
            payload: { action_id: "action-1", name: "bash" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments).toContainEqual(
      expect.objectContaining({
        kind: "decision",
        decision: expect.objectContaining({ state: "completed" }),
      }),
    )
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

  it("projects turn lifecycle transitions from streamed runtime events", () => {
    const queuedState = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "turn.upsert",
      turn: turn("queued"),
    })

    const runningState = agentRuntimeReducer(queuedState, {
      type: "event.append",
      event: {
        ...event("event-started", 1),
        type: "turn.started",
      },
    })

    expect(runningState.turns[0]?.status).toBe("running")
    expect(runningState.status).toBe("running")

    const completedState = agentRuntimeReducer(runningState, {
      type: "event.append",
      event: {
        ...event("event-completed", 2),
        type: "turn.completed",
      },
    })

    expect(completedState.turns[0]?.status).toBe("completed")
    expect(completedState.status).toBe("idle")
  })

  it("promotes queued turns to running when assistant output starts streaming", () => {
    const queuedState = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "turn.upsert",
      turn: turn("queued"),
    })

    const streamingState = agentRuntimeReducer(queuedState, {
      type: "event.append",
      event: {
        ...event("event-stream", 1),
        type: "assistant.text.delta",
        payload: {
          message_id: "message-1",
          delta: "Hello",
          content: "Hello",
          index: 0,
        },
      },
    })

    expect(streamingState.turns[0]?.status).toBe("running")
    expect(streamingState.status).toBe("running")
  })

  it("appends delta-only assistant text chunks", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-1", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", delta: "Hello" },
          },
          {
            ...event("event-2", 2),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", text_delta: " world" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.text).toBe("Hello world")
  })

  it("replaces text when streaming events carry cumulative content", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [{ ...turn("completed"), final_text: "stale final text" }],
        events: [
          {
            ...event("event-1", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", content: "Hello" },
          },
          {
            ...event("event-2", 2),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", content: "Hello world" },
          },
          {
            ...event("event-3", 3),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", text: "Hello world!" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.text).toBe("Hello world!")
  })

  it("keeps newer streamed events when a stale state snapshot loads", () => {
    const running = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session("2026-06-08T00:00:01Z"),
        turns: [turn("running", "2026-06-08T00:00:01Z")],
        events: [
          {
            ...event("event-1", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", delta: "newer streamed text" },
            updated_at: "2026-06-08T00:00:01Z",
          },
        ],
      },
    })

    const merged = agentRuntimeReducer(running, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("queued")],
        events: [],
      },
    })

    expect(merged.events.map((item) => item.id)).toEqual(["event-1"])
    expect(merged.turns[0]?.status).toBe("running")
    expect(merged.timeline[0].assistant.text).toBe("newer streamed text")
  })

  it("keeps approval resume events from leaving turns stuck waiting", () => {
    const waiting = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "turn.upsert",
      turn: turn("queued"),
    })

    const awaitingApproval = agentRuntimeReducer(waiting, {
      type: "event.append",
      event: {
        ...event("event-approval", 1),
        type: "action.waiting_decision",
      },
    })
    expect(awaitingApproval.turns[0]?.status).toBe("waiting_approval")

    const resuming = agentRuntimeReducer(awaitingApproval, {
      type: "event.append",
      event: {
        ...event("event-approved", 2),
        type: "action.decision_recorded",
      },
    })
    expect(resuming.turns[0]?.status).toBe("running")
  })

  it("projects plan approval events into inline plan cards", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("waiting_approval")],
        events: [
          {
            ...event("event-plan", 1),
            type: "action.waiting_decision",
            payload: {
              action_id: "action-plan",
              name: "exit_plan_mode",
              interaction: {
                kind: "plan_approval",
                plan: "1. Inspect files\n2. Apply changes",
              },
            },
          },
        ],
      },
    })

    expect(loaded.timeline[0].inlinePlans).toEqual([
      {
        actionId: "action-plan",
        plan: "1. Inspect files\n2. Apply changes",
        status: "pending",
      },
    ])

    const approved = agentRuntimeReducer(loaded, {
      type: "event.append",
      event: {
        ...event("event-approved", 2),
        type: "action.decision_recorded",
        payload: { action_id: "action-plan", decision: "approve" },
      },
    })

    expect(approved.timeline[0].inlinePlans[0]?.status).toBe("approved")
  })

  it("keeps loaded final text when replaying delta-only text events", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [{ ...turn("running"), final_text: "Persisted answer." }],
        events: [
          {
            ...event("event-delta", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", delta: " More text." },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.textBlocks.map((block) => block.text)).toEqual([
      "Persisted answer.",
      " More text.",
    ])
    expect(loaded.timeline[0].assistant.text).toContain("Persisted answer.")
  })

  it("keeps separate message text blocks around tool calls", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-text-1", 1),
            type: "assistant.text.completed",
            payload: { message_id: "message-0", content: "First text." },
          },
          {
            ...event("event-tool", 2),
            type: "assistant.tool_call.completed",
            payload: {
              message_id: "message-0",
              call_id: "call-1",
              name: "glob",
              status: "completed",
              arguments: { pattern: "**/*.wdl" },
              index: 0,
            },
          },
          {
            ...event("event-text-2", 3),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "Second text." },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.textBlocks.map((block) => block.text)).toEqual([
      "First text.",
      "Second text.",
    ])
    expect(loaded.timeline[0].segments.map((segment) => segment.kind)).toEqual([
      "assistant_text",
      "activity_group",
      "assistant_text",
    ])
  })

  it("keeps text blocks with the same message id ordered around tool calls", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-text-1", 1),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "Before tool." },
          },
          {
            ...event("event-tool", 2),
            type: "assistant.tool_call.completed",
            payload: {
              message_id: "message-1",
              call_id: "call-1",
              name: "glob",
              status: "completed",
              arguments: { pattern: "**/*.wdl" },
              index: 0,
            },
          },
          {
            ...event("event-text-2", 3),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "After tool." },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.textBlocks.map((block) => block.text)).toEqual([
      "Before tool.",
      "After tool.",
    ])
    expect(loaded.timeline[0].segments.map((segment) => segment.kind)).toEqual([
      "assistant_text",
      "activity_group",
      "assistant_text",
    ])
  })

  it("does not leave completed decisions pending without a decision event", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("completed")],
        events: [
          {
            ...event("event-waiting", 1),
            type: "action.waiting_decision",
            payload: { action_id: "action-1", name: "bash" },
          },
          {
            ...event("event-completed", 2),
            type: "action.completed",
            payload: { action_id: "action-1", name: "bash" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments).toContainEqual(
      expect.objectContaining({
        kind: "decision",
        decision: expect.objectContaining({ state: "completed" }),
      }),
    )
    expect(
      loaded.timeline[0].segments.some(
        (segment) => segment.kind === "decision" && segment.status === "pending",
      ),
    ).toBe(false)
  })

  it("accumulates thinking deltas without message ids", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-thinking-1", 1),
            type: "assistant.thinking.delta",
            payload: { text_delta: "Inspect" },
          },
          {
            ...event("event-thinking-2", 2),
            type: "assistant.thinking.delta",
            payload: { text_delta: " files" },
          },
          {
            ...event("event-thinking-3", 3),
            type: "assistant.thinking.completed",
            payload: {},
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.thinking).toEqual({
      content: "Inspect files",
      isComplete: true,
    })
    expect(loaded.timeline[0].assistant.thinkingBlocks).toHaveLength(1)
  })

  it("reports completed assistant status for completed turns with only delta text", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("completed")],
        events: [
          {
            ...event("event-text", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", delta: "Done" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.status).toBe("completed")
  })

  it("completed text only replaces partial text for the same message id", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-1", 1),
            type: "assistant.text.delta",
            payload: { message_id: "message-1", delta: "Draft" },
          },
          {
            ...event("event-2", 2),
            type: "assistant.text.delta",
            payload: { message_id: "message-2", delta: "Other" },
          },
          {
            ...event("event-3", 3),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "Final" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].assistant.textBlocks.map((block) => block.text)).toEqual([
      "Final",
      "Other",
    ])
  })

  it("preserves text tool text tool text ordering in segments", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [turn("running")],
        events: [
          {
            ...event("event-text-1", 1),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "One" },
          },
          {
            ...event("event-tool-1", 2),
            type: "assistant.tool_call.completed",
            payload: { call_id: "call-1", name: "glob", status: "completed", index: 0 },
          },
          {
            ...event("event-text-2", 3),
            type: "assistant.text.completed",
            payload: { message_id: "message-2", content: "Two" },
          },
          {
            ...event("event-tool-2", 4),
            type: "assistant.tool_call.completed",
            payload: { call_id: "call-2", name: "pytest", status: "completed", index: 1 },
          },
          {
            ...event("event-text-3", 5),
            type: "assistant.text.completed",
            payload: { message_id: "message-3", content: "Three" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments.map((segment) => segment.kind)).toEqual([
      "assistant_text",
      "activity_group",
      "assistant_text",
      "activity_group",
      "assistant_text",
    ])
  })

  it("shows failed turn errors as terminal segments alongside text", () => {
    const loaded = agentRuntimeReducer(initialAgentRuntimeState, {
      type: "state.loaded",
      payload: {
        session: session(),
        turns: [{ ...turn("failed"), error_message: "tool failed" }],
        events: [
          {
            ...event("event-text", 1),
            type: "assistant.text.completed",
            payload: { message_id: "message-1", content: "I found an issue." },
          },
          {
            ...event("event-failed", 2),
            type: "turn.failed",
            payload: { error_message: "tool failed" },
          },
        ],
      },
    })

    expect(loaded.timeline[0].segments.map((segment) => segment.kind)).toEqual([
      "assistant_text",
      "turn_error",
    ])
    expect(loaded.timeline[0].segments[1]).toEqual(
      expect.objectContaining({ kind: "turn_error", message: "tool failed" }),
    )
  })
})
