import { readFileSync } from "node:fs"
import { join } from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"

import { parseNDJSON, scheduleReplay } from "@/lib/demo/replay-engine"
import type { DemoTimelineItem } from "@/lib/demo/types"
import type { SessionSnapshot } from "@/lib/agent/contracts"

const snapshot: SessionSnapshot = {
  session: {
    id: "session-1",
    user_id: "demo-user",
    workspace_id: "workspace-demo",
    project_id: "project-demo",
    title: "Demo",
    model: {
      provider: "demo",
      model: "demo-model",
      display_name: "Demo Model",
      supports_vision: true,
      supports_reasoning: true,
      supports_tools: true,
    },
    permission_mode: "ask_dangerous",
    workspace_access: "read_write",
    status: "active",
    created_at: "2026-04-24T09:00:00Z",
    updated_at: "2026-04-24T09:00:00Z",
  },
  runs: [],
  entries: [],
  active_run: null,
}

describe("demo replay engine", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("accepts only the formal Agent event timeline and skips malformed or legacy projections", () => {
    const item: DemoTimelineItem = {
      t: 0,
      kind: "agent",
      event: { type: "snapshot", snapshot },
    }
    const text = [
      JSON.stringify(item),
      "{ definitely not json }",
      JSON.stringify({ t: 10, event: "legacy.delta", data: {} }),
    ].join("\n")

    expect(parseNDJSON(text)).toEqual([item])
  })

  it("keeps the shipped recording on the public protocol with explicit tool metadata", () => {
    const recording = readFileSync(
      join(process.cwd(), "lib/demo/recordings/rnaseq-quant-mini-run.ndjson"),
      "utf8",
    )
    const timeline = parseNDJSON(recording)
    const agentEvents = timeline.flatMap((item) =>
      item.kind === "agent" ? [item.event] : [],
    )
    const tools = agentEvents.flatMap((event) =>
      event.type === "tool.updated" ? [event.tool] : [],
    )

    expect(agentEvents[0]?.type).toBe("snapshot")
    expect(tools).not.toHaveLength(0)
    expect(tools.every((tool) => tool.category === "workflow")).toBe(true)
  })

  it("replays the formal timeline directly in compressed timing order", () => {
    vi.useFakeTimers()
    const events: DemoTimelineItem[] = [
      { t: 0, kind: "agent", event: { type: "snapshot", snapshot } },
      {
        t: 1200,
        kind: "agent",
        event: {
          type: "assistant.delta",
          run_id: "run-1",
          draft_id: "draft-1",
          part_id: "text-1",
          part_type: "text",
          start_offset: 0,
          end_offset: 1,
          delta: "S",
        },
      },
      {
        t: 4200,
        kind: "pipeline",
        status: "running",
        currentTask: "READS_STATS",
        dag: null,
      },
      {
        t: 7600,
        kind: "agent",
        event: {
          type: "run.updated",
          run: {
            id: "run-1",
            session_id: "session-1",
            status: "completed",
            phase: null,
            revision: 2,
            started_at: null,
            completed_at: null,
            termination_reason: "completed",
            error: null,
            created_at: "2026-04-24T09:00:00Z",
            updated_at: "2026-04-24T09:00:01Z",
          },
        },
      },
    ]
    const onEvent = vi.fn()
    const onFinish = vi.fn()

    scheduleReplay(events, { onEvent, onFinish })

    vi.advanceTimersByTime(0)
    expect(onEvent).toHaveBeenNthCalledWith(1, events[0], 0, 4)
    vi.advanceTimersByTime(30)
    expect(onEvent).toHaveBeenNthCalledWith(2, events[1], 1, 4)
    vi.advanceTimersByTime(500)
    expect(onEvent).toHaveBeenNthCalledWith(3, events[2], 2, 4)
    vi.advanceTimersByTime(2000)
    expect(onEvent).toHaveBeenNthCalledWith(4, events[3], 3, 4)
    expect(onFinish).toHaveBeenCalledTimes(1)
  })

  it("cancels any remaining scheduled playback", () => {
    vi.useFakeTimers()
    const events: DemoTimelineItem[] = [
      { t: 0, kind: "agent", event: { type: "snapshot", snapshot } },
      {
        t: 1000,
        kind: "pipeline",
        status: "completed",
        currentTask: null,
        dag: null,
      },
    ]
    const onEvent = vi.fn()
    const onFinish = vi.fn()
    const cancel = scheduleReplay(events, { onEvent, onFinish })

    vi.advanceTimersByTime(0)
    expect(onEvent).toHaveBeenCalledTimes(1)
    cancel()
    vi.advanceTimersByTime(5000)

    expect(onEvent).toHaveBeenCalledTimes(1)
    expect(onFinish).not.toHaveBeenCalled()
  })
})
