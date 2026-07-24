import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { subscribeAgentRuntimeEvents } from "@/lib/agent-runtime"
import type { AgentRuntimeEvent } from "@/lib/agent-runtime"

class MockEventSource {
  static CONNECTING = 0
  static OPEN = 1
  static CLOSED = 2
  static instances: MockEventSource[] = []

  readonly url: string
  readonly options?: EventSourceInit
  readyState = MockEventSource.CONNECTING
  onopen: ((event: Event) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent) => void) | null = null
  closed = false
  private listeners = new Map<string, Set<(event: MessageEvent) => void>>()

  constructor(url: string, options?: EventSourceInit) {
    this.url = url
    this.options = options
    MockEventSource.instances.push(this)
  }

  addEventListener(eventName: string, listener: (event: MessageEvent) => void) {
    const listeners = this.listeners.get(eventName) ?? new Set()
    listeners.add(listener)
    this.listeners.set(eventName, listeners)
  }

  close() {
    this.closed = true
    this.readyState = MockEventSource.CLOSED
  }

  open() {
    this.readyState = MockEventSource.OPEN
    this.onopen?.(new Event("open"))
  }

  error(readyState = this.readyState) {
    this.readyState = readyState
    this.onerror?.(new Event("error"))
  }

  emitNamed(eventName: string, payload?: unknown) {
    const event = {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent
    this.listeners.get(eventName)?.forEach((listener) => listener(event))
  }

  emitMessage(payload: unknown) {
    this.onmessage?.({
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent)
  }
}

function event(seq: number, type = "assistant.content"): AgentRuntimeEvent {
  return {
    id: `event-${seq}`,
    session_id: "session-1",
    turn_id: "turn-1",
    seq,
    type,
    payload: { kind: "text", phase: "delta", text: `chunk-${seq}` },
    visibility: "user",
    schema_version: 1,
    created_at: "2026-07-11T00:00:00Z",
    updated_at: "2026-07-11T00:00:00Z",
  }
}

describe("subscribeAgentRuntimeEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    vi.stubGlobal("EventSource", MockEventSource)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("uses the exact cursor URL, credentials, ready event, and message bindings", () => {
    const onEvent = vi.fn()
    const onReady = vi.fn()
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session/id",
      afterSeq: 4,
      onEvent,
      onReady,
    })
    const source = MockEventSource.instances[0]
    const url = new URL(source.url)

    expect(url.pathname).toBe("/api/v1/agent/sessions/session/id/stream")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      after_seq: "4",
      event_view: "public",
    })
    expect(source.options).toEqual({ withCredentials: true })

    source.emitNamed("ready")
    source.emitMessage(event(5))
    source.emitNamed("assistant.content", event(6))
    source.emitMessage("{bad-json")
    source.emitNamed("assistant.content", "{bad-json")

    expect(onReady).toHaveBeenCalledOnce()
    expect(onEvent).toHaveBeenCalledTimes(2)
    expect(onEvent).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({ seq: 5, type: "assistant.text.delta" }),
    )
    expect(onEvent).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({ seq: 6, type: "assistant.text.delta" }),
    )

    unsubscribe()
  })

  it("advances after_seq monotonically across default and named events", () => {
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session-1",
      afterSeq: 4,
      onEvent: vi.fn(),
    })
    const firstSource = MockEventSource.instances[0]

    firstSource.emitMessage(event(9))
    firstSource.emitNamed(
      "turn.lifecycle",
      event(7, "turn.lifecycle"),
    )
    firstSource.error(MockEventSource.OPEN)
    vi.advanceTimersByTime(1000)

    const nextUrl = new URL(MockEventSource.instances[1].url)
    expect(nextUrl.searchParams.get("after_seq")).toBe("9")

    unsubscribe()
  })

  it("reports and reconnects after any error while closing the failed source", () => {
    const onError = vi.fn()
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session-1",
      afterSeq: 0,
      onEvent: vi.fn(),
      onError,
    })
    const firstSource = MockEventSource.instances[0]

    firstSource.error(MockEventSource.OPEN)
    firstSource.error(MockEventSource.OPEN)

    expect(onError).toHaveBeenCalledTimes(2)
    expect(firstSource.closed).toBe(true)
    expect(vi.getTimerCount()).toBe(1)

    vi.advanceTimersByTime(1000)

    expect(MockEventSource.instances).toHaveLength(2)
    unsubscribe()
  })

  it("uses a 15 second capped backoff", () => {
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session-1",
      afterSeq: 0,
      onEvent: vi.fn(),
    })
    const expectedDelays = [1000, 2000, 4000, 8000, 15000, 15000]

    for (const delay of expectedDelays) {
      const source = MockEventSource.instances.at(-1)!
      source.error(MockEventSource.OPEN)
      vi.advanceTimersByTime(delay - 1)
      expect(MockEventSource.instances.at(-1)).toBe(source)
      vi.advanceTimersByTime(1)
    }

    expect(MockEventSource.instances).toHaveLength(expectedDelays.length + 1)
    unsubscribe()
  })

  it("resets backoff on open and disposes the active source and timer", () => {
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session-1",
      afterSeq: 0,
      onEvent: vi.fn(),
    })
    const firstSource = MockEventSource.instances[0]

    firstSource.error(MockEventSource.OPEN)
    vi.advanceTimersByTime(1000)
    const secondSource = MockEventSource.instances[1]
    secondSource.error(MockEventSource.OPEN)
    vi.advanceTimersByTime(2000)
    const thirdSource = MockEventSource.instances[2]
    thirdSource.open()
    thirdSource.error(MockEventSource.OPEN)
    vi.advanceTimersByTime(999)

    expect(MockEventSource.instances).toHaveLength(3)
    vi.advanceTimersByTime(1)
    expect(MockEventSource.instances).toHaveLength(4)

    const fourthSource = MockEventSource.instances[3]
    fourthSource.error(MockEventSource.OPEN)
    expect(vi.getTimerCount()).toBe(1)

    unsubscribe()

    expect(fourthSource.closed).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    vi.runAllTimers()
    expect(MockEventSource.instances).toHaveLength(4)
  })
})
