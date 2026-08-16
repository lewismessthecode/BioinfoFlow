import { describe, expect, it } from "vitest"

import {
  applyAgentEvent,
  initialAgentStoreState,
} from "@/lib/agent/store"
import type {
  ActiveRunView,
  AgentEvent,
  HistoryEntry,
  RunView,
  SessionSnapshot,
  ToolProgressView,
} from "@/lib/agent/contracts"

const timestamp = "2026-08-15T00:00:00Z"

const run = (overrides: Partial<RunView> = {}): RunView => ({
  id: "run-1",
  session_id: "session-1",
  status: "running",
  phase: "model",
  revision: 1,
  started_at: timestamp,
  completed_at: null,
  termination_reason: null,
  error: null,
  created_at: timestamp,
  updated_at: timestamp,
  ...overrides,
})

const activeRun = (overrides: Partial<ActiveRunView> = {}): ActiveRunView => ({
  run: run(),
  assistant_draft: {
    id: "draft-1",
    run_id: "run-1",
    parts: [
      {
        id: "part-1",
        type: "text",
        text: "Hello",
        end_offset: 5,
      },
    ],
  },
  tool_progress: [],
  pending_interaction: null,
  ...overrides,
})

const snapshot = (overrides: Partial<SessionSnapshot> = {}): SessionSnapshot => ({
  session: {
    id: "session-1",
    user_id: "user-1",
    workspace_id: "workspace-1",
    project_id: "project-1",
    title: "Analysis",
    model: {
      provider: "openai",
      model: "gpt-5.6",
      display_name: "GPT-5.6",
      supports_vision: true,
      supports_reasoning: true,
      supports_tools: true,
    },
    permission_mode: "ask_dangerous",
    workspace_access: "read_write",
    status: "active",
    created_at: timestamp,
    updated_at: timestamp,
  },
  runs: [run()],
  entries: [],
  active_run: activeRun(),
  ...overrides,
})

function apply(state: ReturnType<typeof snapshotState>, event: AgentEvent) {
  return applyAgentEvent(state, event)
}

function snapshotState(value: SessionSnapshot = snapshot()) {
  return applyAgentEvent(initialAgentStoreState, {
    type: "snapshot",
    snapshot: value,
  }).state
}

describe("applyAgentEvent", () => {
  it("replaces all authoritative state from a snapshot", () => {
    const replacement = snapshot({
      session: {
        ...snapshot().session,
        title: "Replacement",
      },
      entries: [userEntry("entry-1", 1)],
    })

    const result = applyAgentEvent(
      {
        ...snapshotState(),
        entries: [userEntry("stale", 99)],
      },
      { type: "snapshot", snapshot: replacement },
    )

    expect(result.outcome).toBe("applied")
    expect(result.state).toEqual({
      session: replacement.session,
      runs: replacement.runs,
      entries: replacement.entries,
      activeRun: replacement.active_run,
    })
    expect("historyRevision" in result.state).toBe(false)
  })

  it("applies run updates by run-local revision without a global revision gate", () => {
    const state = snapshotState()

    const result = apply(state, {
      type: "run.updated",
      run: run({ status: "waiting_user", phase: "interaction", revision: 2 }),
    })

    expect(result.outcome).toBe("applied")
    expect(result.state.runs[0]).toMatchObject({
      status: "waiting_user",
      phase: "interaction",
      revision: 2,
    })
    expect(result.state.activeRun?.run).toMatchObject({
      status: "waiting_user",
      revision: 2,
    })
  })

  it("creates the active run when the first live event is a non-terminal run update", () => {
    const state = {
      ...snapshotState(),
      runs: [],
      activeRun: null,
    }
    const started = run({ revision: 1, status: "running", phase: "model" })

    const result = apply(state, { type: "run.updated", run: started })

    expect(result.outcome).toBe("applied")
    expect(result.state.activeRun).toEqual({
      run: started,
      assistant_draft: null,
      tool_progress: [],
      pending_interaction: null,
    })
  })

  it("creates a draft and part from a first contiguous assistant delta", () => {
    const state = {
      ...snapshotState(),
      activeRun: {
        run: run(),
        assistant_draft: null,
        tool_progress: [],
        pending_interaction: null,
      },
    }

    const result = apply(state, {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-new",
      part_id: "part-new",
      part_type: "reasoning_summary",
      start_offset: 0,
      end_offset: 8,
      delta: "Checking",
    })

    expect(result.outcome).toBe("applied")
    expect(result.state.activeRun?.assistant_draft).toEqual({
      id: "draft-new",
      run_id: "run-1",
      parts: [
        {
          id: "part-new",
          type: "reasoning_summary",
          text: "Checking",
          end_offset: 8,
        },
      ],
    })
  })

  it("preserves reasoning provenance when a live trace starts", () => {
    const state = {
      ...snapshotState(),
      activeRun: {
        run: run(),
        assistant_draft: null,
        tool_progress: [],
        pending_interaction: null,
      },
    }

    const result = apply(state, {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-reasoning",
      part_id: "trace-1",
      part_type: "reasoning_trace",
      start_offset: 0,
      end_offset: 12,
      delta: "Trace clues",
      provider: "openai",
      model: "gpt-5.6",
      source: "reasoning_content",
      truncated: false,
      started_at: timestamp,
      completed_at: null,
    })

    expect(result.state.activeRun?.assistant_draft?.parts[0]).toEqual({
      id: "trace-1",
      type: "reasoning_trace",
      text: "Trace clues",
      end_offset: 12,
      provider: "openai",
      model: "gpt-5.6",
      source: "reasoning_content",
      truncated: false,
      started_at: timestamp,
      completed_at: null,
    })
  })

  it("appends a contiguous assistant delta to the identified draft part", () => {
    const result = apply(snapshotState(), {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-1",
      part_id: "part-1",
      part_type: "text",
      start_offset: 5,
      end_offset: 11,
      delta: " world",
    })

    expect(result.outcome).toBe("applied")
    expect(result.state.activeRun?.assistant_draft?.parts[0]).toEqual({
      id: "part-1",
      type: "text",
      text: "Hello world",
      end_offset: 11,
    })
  })

  it("ignores an assistant delta already covered by the local part offset", () => {
    const state = snapshotState()
    const result = apply(state, {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-1",
      part_id: "part-1",
      part_type: "text",
      start_offset: 0,
      end_offset: 5,
      delta: "Hello",
    })

    expect(result).toEqual({ outcome: "ignored", state })
  })

  it.each([
    ["gap", 6, 12],
    ["overlap", 4, 10],
  ])("returns needs_snapshot for a delta %s", (_label, startOffset, endOffset) => {
    const state = snapshotState()
    const result = apply(state, {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-1",
      part_id: "part-1",
      part_type: "text",
      start_offset: startOffset,
      end_offset: endOffset,
      delta: " world",
    })

    expect(result).toEqual({ outcome: "needs_snapshot", state })
  })

  it("upserts tool progress by call id and ignores stale call-local revisions", () => {
    const pending = tool({ revision: 2, status: "running" })
    const withTool = apply(snapshotState(), {
      type: "tool.updated",
      run_id: "run-1",
      tool: pending,
    })

    expect(withTool.state.activeRun?.tool_progress).toEqual([pending])

    const stale = apply(withTool.state, {
      type: "tool.updated",
      run_id: "run-1",
      tool: tool({ revision: 1, status: "pending" }),
    })

    expect(stale.outcome).toBe("ignored")
    expect(stale.state).toBe(withTool.state)
  })

  it("replaces the pending interaction using its interaction-local revision", () => {
    const result = apply(snapshotState(), {
      type: "interaction.requested",
      run_id: "run-1",
      interaction: {
        interaction_id: "interaction-1",
        run_id: "run-1",
        revision: 1,
        request: {
          type: "ask_user",
          call_id: "ask-1",
          questions: [
            {
              id: "sample",
              header: "Sample",
              question: "Which sample?",
              multi_select: false,
              options: [
                {
                  id: "sample-a",
                  label: "Sample A",
                  description: "Use the first sample",
                  recommended: true,
                },
                {
                  id: "sample-b",
                  label: "Sample B",
                  description: "Use the second sample",
                  recommended: false,
                },
              ],
            },
          ],
        },
      },
    })

    expect(result.outcome).toBe("applied")
    expect(result.state.activeRun?.pending_interaction).toMatchObject({
      interaction_id: "interaction-1",
      request: {
        type: "ask_user",
        questions: [{ id: "sample", question: "Which sample?" }],
      },
    })
  })

  it("ignores an exact duplicate committed entry", () => {
    const entry = userEntry("entry-2", 2)
    const state = snapshotState(
      snapshot({
        entries: [entry],
      }),
    )
    const duplicate = apply(state, { type: "entry.committed", entry })

    expect(duplicate.outcome).toBe("ignored")
    expect(duplicate.state).toBe(state)
  })

  it("ignores a stale committed entry even when its id was not seen", () => {
    const state = snapshotState(
      snapshot({ entries: [userEntry("entry-2", 2)] }),
    )

    const stale = apply(state, {
      type: "entry.committed",
      entry: userEntry("late-entry-1", 1),
    })

    expect(stale).toEqual({ outcome: "ignored", state })
  })

  it("requests a snapshot for a sequence gap and accepts the entries in order", () => {
    const state = snapshotState(
      snapshot({ entries: [userEntry("entry-2", 2)] }),
    )
    const outOfOrder = userEntry("entry-4", 4)

    const gap = apply(state, { type: "entry.committed", entry: outOfOrder })
    expect(gap).toEqual({ outcome: "needs_snapshot", state })

    const next = apply(state, {
      type: "entry.committed",
      entry: userEntry("entry-3", 3),
    })
    expect(next.outcome).toBe("applied")
    expect(next.state.entries.map((entry) => entry.sequence)).toEqual([2, 3])

    const retried = apply(next.state, {
      type: "entry.committed",
      entry: outOfOrder,
    })
    expect(retried.outcome).toBe("applied")
    expect(retried.state.entries.map((entry) => entry.sequence)).toEqual([
      2, 3, 4,
    ])
  })

  it("removes the matching assistant draft when its durable message is committed", () => {
    const entry: HistoryEntry = {
      id: "assistant-entry",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 2,
      schema_version: 2,
      created_at: timestamp,
      type: "message",
      payload: {
        role: "assistant",
        parts: [{ id: "assistant-text", type: "text", text: "Hello" }],
      },
    }

    const result = apply(
      snapshotState(snapshot({ entries: [userEntry("entry-1", 1)] })),
      { type: "entry.committed", entry },
    )

    expect(result.state.activeRun?.assistant_draft).toBeNull()
  })

  it("removes only tool progress represented by a committed tool result", () => {
    const first = tool({ call_id: "call-1" })
    const second = tool({ call_id: "call-2" })
    const state = snapshotState(
      snapshot({
        entries: [userEntry("entry-1", 1)],
        active_run: activeRun({ tool_progress: [first, second] }),
      }),
    )
    const entry: HistoryEntry = {
      id: "tool-entry",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 2,
      schema_version: 2,
      created_at: timestamp,
      type: "message",
      payload: {
        role: "tool",
        parts: [
          {
            id: "tool-result",
            type: "tool_result",
            call_id: "call-1",
            status: "completed",
            summary: "Read configuration",
            output: null,
            started_at: timestamp,
            completed_at: timestamp,
            error: null,
          },
        ],
      },
    }

    const result = apply(state, { type: "entry.committed", entry })

    expect(result.state.activeRun?.tool_progress).toEqual([second])
  })

  it("clears a pending interaction when its durable response is committed", () => {
    const state = snapshotState(
      snapshot({
        entries: [userEntry("entry-1", 1)],
        active_run: activeRun({
          pending_interaction: {
            interaction_id: "interaction-1",
            run_id: "run-1",
            revision: 1,
            request: {
              type: "approval",
              call_id: "call-1",
              tool_name: "bash",
              summary: "Run command",
              input_preview: "bif run",
              allowed_responses: ["approve", "reject"],
              risk: {
                level: "high",
                effects: ["Runs a workflow"],
                reasons: ["Creates external work"],
                affected_resources: ["workspace"],
              },
            },
          },
        }),
      }),
    )
    const entry: HistoryEntry = {
      id: "interaction-response",
      session_id: "session-1",
      run_id: "run-1",
      sequence: 2,
      schema_version: 2,
      created_at: timestamp,
      type: "interaction_response",
      payload: {
        interaction_id: "interaction-1",
        response: { type: "approval", approved: true },
      },
    }

    const result = apply(state, { type: "entry.committed", entry })

    expect(result.state.activeRun?.pending_interaction).toBeNull()
  })

  it("removes the active run after an authoritative terminal run update", () => {
    const result = apply(snapshotState(), {
      type: "run.updated",
      run: run({
        status: "completed",
        phase: null,
        revision: 2,
        completed_at: timestamp,
      }),
    })

    expect(result.state.runs[0]?.status).toBe("completed")
    expect(result.state.activeRun).toBeNull()
  })
})

function userEntry(id: string, sequence: number): HistoryEntry {
  return {
    id,
    session_id: "session-1",
    run_id: "run-1",
    sequence,
    schema_version: 1,
    created_at: timestamp,
    type: "message",
    payload: {
      role: "user",
      parts: [{ id: `${id}-text`, type: "text", text: "Hello" }],
    },
  }
}

function tool(overrides: Partial<ToolProgressView> = {}): ToolProgressView {
  return {
    call_id: "call-1",
    group_id: "group-1",
    execution_mode: "parallel",
    name: "read_file",
    display_name: "Read file",
    category: "read",
    summary: "Read configuration",
    arguments: { path: "config.json" },
    status: "pending",
    revision: 1,
    started_at: null,
    completed_at: null,
    input_summary: null,
    output_summary: null,
    error: null,
    ...overrides,
  }
}
