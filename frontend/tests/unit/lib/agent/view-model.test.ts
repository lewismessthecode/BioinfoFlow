import { describe, expect, it } from "vitest"

import { buildTranscriptView, scopeLiveToolsByEntry } from "@/lib/agent/view-model"
import type { HistoryEntry, ToolProgressView } from "@/lib/agent/contracts"

describe("Agent transcript view model", () => {
  it("sorts canonical entries and derives durable relationships without mutation", () => {
    const entries: HistoryEntry[] = [
      message("tool-result", 3, "tool", [
        {
          id: "result-part",
          type: "tool_result",
          call_id: "call-1",
          status: "completed",
          summary: "done",
          error: null,
          output: null,
          public_details: [],
          started_at: null,
          completed_at: null,
        },
      ]),
      message("assistant", 2, "assistant", [
        {
          id: "call-part",
          type: "tool_call",
          call_id: "call-1",
          group_id: "group-1",
          execution_mode: "serial",
          name: "read",
          display_name: "Read",
          category: "read",
          summary: "Read a file",
          public_details: [],
        },
      ]),
      message("user", 1, "user", [
        { id: "text-part", type: "text", text: "Inspect it" },
      ]),
    ]

    const view = buildTranscriptView(entries)

    expect(view.entries.map((entry) => entry.id)).toEqual([
      "user",
      "assistant",
      "tool-result",
    ])
    expect(view.toolResultsByCallId.get("call-1")?.summary).toBe("done")
    expect(view.toolCallEntryIdsByCallId.get("call-1")).toBe("assistant")
    expect(view.visibleMessagePartsByEntryId.get("tool-result")).toEqual([])
    expect(entries.map((entry) => entry.id)).toEqual([
      "tool-result",
      "assistant",
      "user",
    ])
  })

  it("scopes live tools to the durable entry that owns each call", () => {
    const tool = {
      call_id: "call-1",
      status: "running",
      revision: 2,
    } as ToolProgressView

    const scoped = scopeLiveToolsByEntry(
      new Map([[tool.call_id, tool]]),
      new Map([[tool.call_id, "assistant"]]),
    )

    expect(scoped.get("assistant")?.get("call-1")).toBe(tool)
  })
})

function message(
  id: string,
  sequence: number,
  role: "user" | "assistant" | "tool",
  parts: Extract<HistoryEntry, { type: "message" }>["payload"]["parts"],
): HistoryEntry {
  return {
    id,
    session_id: "session-1",
    run_id: "run-1",
    sequence,
    schema_version: 2,
    created_at: `2026-08-16T00:00:0${sequence}Z`,
    type: "message",
    payload: { role, parts },
  }
}
