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
})
