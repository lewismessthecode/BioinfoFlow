import { afterEach, describe, expect, it, vi } from "vitest"

import { parseNDJSON, scheduleReplay } from "@/lib/demo/replay-engine"
import type { RecordedEvent } from "@/lib/demo/types"

describe("demo replay engine", () => {
  afterEach(() => {
    vi.useRealTimers()
  })

  it("parses NDJSON while skipping malformed lines", () => {
    const text = [
      JSON.stringify({ t: 0, event: "user.message", data: { content: "hello" } }),
      "{ definitely not json }",
      JSON.stringify({ t: 100, event: "agent.done", data: { id: "msg-1" } }),
    ].join("\n")

    expect(parseNDJSON(text)).toEqual([
      { t: 0, event: "user.message", data: { content: "hello" } },
      { t: 100, event: "agent.done", data: { id: "msg-1" } },
    ])
  })

  it("replays events in compressed timing order and fires onFinish after the last item", () => {
    vi.useFakeTimers()

    const events: RecordedEvent[] = [
      { t: 0, event: "user.message", data: { content: "run qc" } },
      { t: 1200, event: "agent.text_delta", data: { id: "msg-1", content: "S" } },
      { t: 4200, event: "run.status", data: { run_id: "run-1", status: "running" } },
      { t: 7600, event: "agent.done", data: { id: "msg-1" } },
    ]

    const onEvent = vi.fn()
    const onFinish = vi.fn()

    scheduleReplay(events, { onEvent, onFinish })

    vi.advanceTimersByTime(0)
    expect(onEvent).toHaveBeenNthCalledWith(
      1,
      { kind: "user_message", text: "run qc" },
      0,
      4,
    )

    vi.advanceTimersByTime(30)
    expect(onEvent).toHaveBeenNthCalledWith(
      2,
      {
        kind: "agent",
        agentEvent: {
          type: "assistant.text.delta",
          source_id: "msg-1",
          payload: { text_delta: "S" },
          final_text_delta: "S",
        },
      },
      1,
      4,
    )

    vi.advanceTimersByTime(500)
    expect(onEvent).toHaveBeenNthCalledWith(
      3,
      {
        kind: "run_status",
        data: { run_id: "run-1", status: "running" },
      },
      2,
      4,
    )

    vi.advanceTimersByTime(2000)
    expect(onEvent).toHaveBeenNthCalledWith(
      4,
      {
        kind: "agent",
        agentEvent: {
          type: "turn.completed",
          source_id: "msg-1",
          payload: {},
        },
      },
      3,
      4,
    )
    expect(onFinish).toHaveBeenCalledTimes(1)
  })

  it("cancels any remaining scheduled playback", () => {
    vi.useFakeTimers()

    const events: RecordedEvent[] = [
      { t: 0, event: "user.message", data: { content: "step 1" } },
      { t: 1000, event: "agent.text.completed", data: { id: "msg-1", content: "step 2" } },
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
