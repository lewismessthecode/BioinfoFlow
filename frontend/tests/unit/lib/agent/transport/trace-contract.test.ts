import { describe, expect, it } from "vitest"

import {
  parseAgentTraceDetail,
  parseAgentTraceTimeline,
  type AgentTraceTimelineContract,
} from "@/lib/agent/transport/trace-contract"

const timestamp = "2026-08-17T08:00:00.000Z"

function timelineFixture(): AgentTraceTimelineContract {
  return {
    protocol: "bioinfoflow.agent.trace",
    protocol_version: 1,
    session: {
      id: "session-1",
      title: "RNA-seq review",
      status: "active",
      model: {
        provider: "openai",
        model: "gpt-5.6",
        display_name: "GPT-5.6",
      },
      created_at: timestamp,
      updated_at: timestamp,
    },
    turns: [
      {
        id: "turn-1",
        run_id: "run-1",
        index: 1,
        status: "completed",
        model: {
          provider: "openai",
          model: "gpt-5.6",
          display_name: "GPT-5.6",
        },
        started_at: timestamp,
        completed_at: timestamp,
      },
    ],
    context_flow: [
      {
        id: "context-1",
        turn_id: "turn-1",
        model_trace_id: "model:trace-1",
        sequence: 1,
        through_sequence: 3,
        compacted: false,
        input_tokens: null,
        output_tokens: null,
        cached_input_tokens: null,
        reasoning_tokens: null,
        total_tokens: null,
        max_context_tokens: null,
        composition: [
          {
            category: "system",
            characters: 120,
            tokens: null,
          },
        ],
        created_at: timestamp,
      },
    ],
    events: [
      {
        id: "entry:user-1",
        turn_id: "turn-1",
        category: "user",
        title: "User",
        summary: "Inspect the FASTQ files exactly as received.",
        status: "completed",
        sequence: 1,
        has_detail: true,
        created_at: timestamp,
      },
    ],
  }
}

describe("Agent Trace transport contract", () => {
  it("accepts the stable timeline contract and preserves unavailable telemetry as null", () => {
    const timeline = timelineFixture()
    timeline.events[0].sequence = 2
    timeline.events.unshift({
      id: "system:session-1",
      turn_id: null,
      category: "system",
      title: "System",
      summary: "You are BioinfoFlow.",
      status: null,
      sequence: 1,
      has_detail: true,
      created_at: timestamp,
    })
    const parsed = parseAgentTraceTimeline(timeline)

    expect(parsed.ok).toBe(true)
    if (!parsed.ok) return
    expect(parsed.value.context_flow[0]).toMatchObject({
      input_tokens: null,
      output_tokens: null,
      cached_input_tokens: null,
      reasoning_tokens: null,
      total_tokens: null,
      max_context_tokens: null,
    })
    expect(parsed.value.events[0]).toMatchObject({
      turn_id: null,
      status: null,
    })
  })

  it("rejects malformed timeline data before it reaches the Trace UI", () => {
    const malformed = timelineFixture()
    malformed.events[0].sequence = -1

    expect(parseAgentTraceTimeline(malformed)).toEqual({
      ok: false,
      error: expect.objectContaining({ code: "invalid_payload" }),
    })
  })

  it("rejects malformed optional usage before it reaches the Trace UI", () => {
    const malformed = timelineFixture() as AgentTraceTimelineContract & {
      context_flow: Array<{ output_tokens: unknown }>
    }
    malformed.context_flow[0].output_tokens = -1

    expect(parseAgentTraceTimeline(malformed)).toEqual({
      ok: false,
      error: expect.objectContaining({ code: "invalid_payload" }),
    })
  })

  it("accepts exact raw event detail without applying Presentation Contract rules", () => {
    const detail = {
      protocol: "bioinfoflow.agent.trace",
      protocol_version: 1,
      event_id: "entry:tool-1",
      summary: {
        category: "tool",
        parent_event_id: "model:trace-1",
        child_event_ids: ["entry:tool-result-1"],
      },
      payload: {
        name: "nextflow_run",
        arguments: { pipeline: "main.nf", resume: true },
      },
      result: { run_id: "run-1", status: "completed" },
      schema: { type: "object", required: ["pipeline"] },
      timing: {
        started_at: timestamp,
        request_prepared_at: "2026-08-17T08:00:00.100Z",
        first_byte_at: "2026-08-17T08:00:00.300Z",
        completed_at: "2026-08-17T08:00:01.250Z",
        duration_ms: 1250,
      },
    }

    expect(parseAgentTraceDetail(detail)).toEqual({ ok: true, value: detail })
  })
})
