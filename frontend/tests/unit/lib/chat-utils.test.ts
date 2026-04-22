import { describe, expect, it } from "vitest"

import { applySSEEvent } from "@/lib/chat-utils"
import type { ChatMessage } from "@/lib/chat-types"

describe("applySSEEvent", () => {
  it("keeps thinking, tool progress, and structured tool results on one assistant message", () => {
    let messages: ChatMessage[] = []

    messages = applySSEEvent(messages, {
      type: "thinking_delta",
      messageId: "response-1",
      content: "Planning the run.",
    })
    messages = applySSEEvent(messages, {
      type: "text_delta",
      messageId: "response-1",
      content: "I am checking the workflow.",
    })
    messages = applySSEEvent(messages, {
      type: "tool_call_start",
      messageId: "response-1",
      metadata: {
        id: "tool-1",
        name: "submit_run",
        args: { workflow_name: "nf-core/rnaseq" },
      },
    })
    messages = applySSEEvent(messages, {
      type: "tool_call_progress",
      messageId: "response-1",
      metadata: {
        id: "tool-1",
        name: "submit_run",
        status: "requires_approval",
        preview: "Waiting for approval",
      },
    })
    messages = applySSEEvent(messages, {
      type: "tool_call_end",
      messageId: "response-1",
      metadata: {
        id: "tool-1",
        name: "submit_run",
        result: JSON.stringify({ run_id: "run_demo_001", status: "queued" }),
        result_json: { run_id: "run_demo_001", status: "queued" },
        is_error: false,
        duration_ms: 1400,
      },
    })

    expect(messages).toHaveLength(1)
    expect(messages[0]?.id).toBe("response-1")
    expect(messages[0]?.parts[0]).toMatchObject({
      type: "thinking",
      text: "Planning the run.",
    })

    const toolPart = messages[0]?.parts.find((part) => part.type === "tool-call")
    expect(toolPart).toMatchObject({
      type: "tool-call",
      id: "tool-1",
      toolName: "submit_run",
      status: "done",
      progressText: "Waiting for approval",
      progressStatus: "requires_approval",
      durationMs: 1400,
    })
    expect(toolPart && "resultData" in toolPart ? toolPart.resultData : undefined).toEqual({
      run_id: "run_demo_001",
      status: "queued",
    })
  })
})
