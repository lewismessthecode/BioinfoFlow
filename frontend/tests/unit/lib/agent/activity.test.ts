import { describe, expect, it } from "vitest"

import {
  buildActiveActivity,
  collectDurableToolCallIds,
} from "@/lib/agent/activity"
import type {
  AssistantDraftPartView,
  HistoryEntry,
  ToolProgressView,
} from "@/lib/agent/contracts"

const timestamp = "2026-08-16T00:00:00Z"

const tool = (
  callId: string,
  groupId: string,
  summary: string,
): ToolProgressView => ({
  call_id: callId,
  group_id: groupId,
  execution_mode: "serial",
  name: "read",
  display_name: "Read",
  category: "read",
  summary,
  arguments: {},
  status: "running",
  revision: 1,
  started_at: timestamp,
  completed_at: null,
  input_summary: null,
  output_summary: null,
  error: null,
})

describe("buildActiveActivity", () => {
  it("preserves the model-provided order of response and thinking parts", () => {
    const parts: AssistantDraftPartView[] = [
      { id: "text-1", type: "text", text: "First", end_offset: 5 },
      {
        id: "thinking-1",
        type: "reasoning_summary",
        text: "Checking",
        end_offset: 8,
      },
      { id: "text-2", type: "text", text: "Last", end_offset: 4 },
    ]

    expect(buildActiveActivity(parts, []).map((item) => item.kind)).toEqual([
      "response",
      "thinking",
      "response",
    ])
  })

  it("groups only adjacent tools and never moves later tools beside an earlier group", () => {
    const activity = buildActiveActivity([], [
      tool("call-a1", "group-a", "A1"),
      tool("call-b", "group-b", "B"),
      tool("call-a2", "group-a", "A2"),
    ])

    expect(
      activity.map((item) =>
        item.kind === "tool_group"
          ? item.tools.map((entry) => entry.summary)
          : item.kind,
      ),
    ).toEqual([["A1"], ["B"], ["A2"]])
  })

  it("omits live tools already represented by a durable tool call", () => {
    const activity = buildActiveActivity(
      [],
      [
        tool("durable-call", "group-a", "Already in history"),
        tool("recovered-call", "group-b", "Recovered live tool"),
      ],
      new Set(["durable-call"]),
    )

    expect(
      activity.flatMap((item) =>
        item.kind === "tool_group"
          ? item.tools.map((entry) => entry.call_id)
          : [],
      ),
    ).toEqual(["recovered-call"])
  })
})

describe("collectDurableToolCallIds", () => {
  it("collects tool calls from sequence-ordered durable entries", () => {
    const entries: HistoryEntry[] = [
      {
        id: "assistant-1",
        session_id: "session-1",
        run_id: "run-1",
        sequence: 1,
        schema_version: 1,
        created_at: timestamp,
        type: "message",
        payload: {
          role: "assistant",
          parts: [
            {
              id: "call-part-1",
              type: "tool_call",
              call_id: "call-1",
              group_id: "group-1",
              execution_mode: "serial",
              name: "read",
              display_name: "Read",
              category: "read",
              summary: "Read workflow.nf",
              arguments: {},
            },
          ],
        },
      },
    ]

    expect([...collectDurableToolCallIds(entries)]).toEqual(["call-1"])
  })
})
