import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { useAgentTrace } from "@/hooks/use-agent-trace"

const mocks = vi.hoisted(() => ({
  timeline: vi.fn(),
  detail: vi.fn(),
}))

vi.mock("@/lib/agent/client", () => ({
  getAgentTraceTimeline: (...args: unknown[]) => mocks.timeline(...args),
  getAgentTraceDetail: (...args: unknown[]) => mocks.detail(...args),
}))

const timestamp = "2026-08-17T08:00:00.000Z"
const timeline = {
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
  turns: [],
  context_flow: [],
  events: [],
}
const detail = {
  protocol: "bioinfoflow.agent.trace",
  protocol_version: 1,
  event_id: "entry:tool-1",
  summary: { category: "tool" },
  payload: { name: "nextflow_run" },
  result: null,
  schema: null,
  timing: null,
}

describe("useAgentTrace", () => {
  beforeEach(() => {
    mocks.timeline.mockReset()
    mocks.detail.mockReset()
    mocks.timeline.mockResolvedValue(timeline)
    mocks.detail.mockResolvedValue(detail)
  })

  it("loads the timeline on mount and projects event detail on demand", async () => {
    const { result } = renderHook(() => useAgentTrace("session-1"))

    await waitFor(() => expect(result.current.view).not.toBeNull())

    let projectedDetail
    await act(async () => {
      projectedDetail = await result.current.loadDetail("entry:tool-1")
    })

    expect(projectedDetail).toMatchObject({
      eventId: "entry:tool-1",
      payload: { name: "nextflow_run" },
      timing: null,
    })
  })

  it("reports malformed Trace payloads without exposing transport data", async () => {
    mocks.timeline.mockResolvedValue({ protocol: "other", protocol_version: 1 })
    const { result } = renderHook(() => useAgentTrace("session-1"))

    await waitFor(() => expect(result.current.error).not.toBeNull())
    expect(result.current.view).toBeNull()
    expect(result.current.error?.message).toContain("protocol")
  })
})
