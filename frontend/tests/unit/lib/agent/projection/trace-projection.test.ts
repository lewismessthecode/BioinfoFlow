import { describe, expect, it } from "vitest"

import { createAgentTraceView } from "@/lib/agent/projection/trace-projection"

const timestamp = "2026-08-17T08:00:00.000Z"

function event(
  id: string,
  category: string,
  sequence: number,
  summary: string,
) {
  return {
    id,
    turn_id: "turn-1",
    category,
    title: category,
    summary,
    status: "completed",
    sequence,
    has_detail: true,
    created_at: timestamp,
  }
}

function timelineFixture() {
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
        model: null,
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
        through_sequence: 5,
        compacted: false,
        input_tokens: null,
        cached_input_tokens: null,
        max_context_tokens: null,
        composition: [
          { category: "system", characters: 100, tokens: null },
          { category: "user", characters: 40, tokens: null },
        ],
        created_at: timestamp,
      },
    ],
    events: [
      {
        ...event("system:session-1", "system", 1, "You are BioinfoFlow"),
        turn_id: null,
        status: null,
      },
      event("assistant:final", "assistant", 5, "Final answer\nsecond line"),
      event("tool:1", "tool", 4, "nextflow_run({ pipeline: 'main.nf' })"),
      event("user:1", "user", 2, "Run the workflow"),
      event("assistant:work", "assistant", 3, "I will inspect the inputs"),
    ],
  }
}

describe("Agent Trace projection", () => {
  it("orders events, groups them by Turn, and derives quiet phase headings", () => {
    const projected = createAgentTraceView(timelineFixture())

    expect(projected.ok).toBe(true)
    if (!projected.ok) return
    expect(projected.view.preambleEvents).toEqual([
      expect.objectContaining({
        id: "system:session-1",
        turnId: null,
        category: "system",
        status: null,
        phase: "pre_call",
      }),
    ])
    expect(projected.view.turns[0].events.map((item) => item.id)).toEqual([
      "user:1",
      "assistant:work",
      "tool:1",
      "assistant:final",
    ])
    expect(projected.view.turns[0].events.map((item) => item.phase)).toEqual([
      "user_input",
      "agent_work",
      "agent_work",
      "final_response",
    ])
    expect(projected.view.turns[0].events.at(-1)?.firstLine).toBe(
      "Final answer",
    )
  })

  it("does not invent token totals, context capacity, or cache hits", () => {
    const projected = createAgentTraceView(timelineFixture())

    expect(projected.ok).toBe(true)
    if (!projected.ok) return
    expect(projected.view.contextFlow[0]).toMatchObject({
      inputTokens: null,
      cachedInputTokens: null,
      maxContextTokens: null,
    })
    expect(projected.view.contextFlow[0].composition[0].tokens).toBeNull()
  })

  it("keeps events from an unknown Turn visible as session events", () => {
    const payload = timelineFixture()
    payload.events.push({
      ...event("future:1", "future_event", 6, "Future adapter event"),
      turn_id: "turn-from-another-adapter",
    })

    const projected = createAgentTraceView(payload)

    expect(projected.ok).toBe(true)
    if (!projected.ok) return
    expect(projected.view.preambleEvents.at(-1)).toEqual(
      expect.objectContaining({
        id: "future:1",
        category: "unknown",
        firstLine: "Future adapter event",
      }),
    )
  })
})
