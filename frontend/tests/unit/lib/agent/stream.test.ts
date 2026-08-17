import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { subscribeAgentEvents } from "@/lib/agent/stream"

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

  error() {
    this.onerror?.(new Event("error"))
  }

  emit(eventName: string, payload: unknown) {
    const event = {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent
    this.listeners.get(eventName)?.forEach((listener) => listener(event))
  }
}

describe("subscribeAgentEvents", () => {
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

  it("connects to the snapshot-first event stream without a replay cursor", () => {
    const onEvent = vi.fn()
    const onDiagnostic = vi.fn()
    const onConnectionChange = vi.fn()
    const unsubscribe = subscribeAgentEvents({
      sessionId: "session/id",
      onEvent,
      onDiagnostic,
      onConnectionChange,
    })
    const source = MockEventSource.instances[0]
    const url = new URL(source.url)

    expect(url.pathname).toBe("/api/v1/agent/sessions/session/id/events")
    expect([...url.searchParams]).toEqual([])
    expect(source.options).toEqual({ withCredentials: true })

    source.open()
    source.emit("assistant.delta", {
      type: "assistant.delta",
      run_id: "run-1",
      draft_id: "draft-1",
      part_id: "part-1",
      part_type: "text",
      start_offset: 0,
      end_offset: 2,
      delta: "Hi",
    })
    source.emit("assistant.delta", "{bad-json")

    expect(onConnectionChange).toHaveBeenCalledWith("connected")
    expect(onEvent).toHaveBeenCalledOnce()
    expect(onEvent).toHaveBeenCalledWith(
      expect.objectContaining({ type: "assistant.delta", delta: "Hi" }),
    )
    expect(onDiagnostic).toHaveBeenCalledWith(
      expect.objectContaining({
        code: "invalid_payload",
        params: { originalType: "assistant.delta" },
      }),
    )

    unsubscribe()
    expect(source.closed).toBe(true)
  })

  it("reports an unknown Harness event as a diagnostic instead of forwarding it", () => {
    const onEvent = vi.fn()
    const onDiagnostic = vi.fn()
    const unsubscribe = subscribeAgentEvents({
      sessionId: "session-1",
      onEvent,
      onDiagnostic,
    })

    MockEventSource.instances[0].emit("run.updated", {
      type: "harness.checkpoint.rotated",
      opaque: true,
    })

    expect(onEvent).not.toHaveBeenCalled()
    expect(onDiagnostic).toHaveBeenCalledWith({
      code: "unknown_event_type",
      message:
        "Unsupported Agent presentation event: harness.checkpoint.rotated",
      originalType: "harness.checkpoint.rotated",
      params: { originalType: "harness.checkpoint.rotated" },
    })
    unsubscribe()
  })

  it("delegates reconnect recovery to the owning session hook", () => {
    const onConnectionChange = vi.fn()
    const onError = vi.fn()
    const unsubscribe = subscribeAgentEvents({
      sessionId: "session-1",
      onEvent: vi.fn(),
      onConnectionChange,
      onError,
    })

    const source = MockEventSource.instances[0]
    source.error()
    expect(onConnectionChange).toHaveBeenCalledWith("reconnecting")
    expect(onError).toHaveBeenCalledOnce()
    expect(source.closed).toBe(true)

    vi.advanceTimersByTime(15_000)

    expect(MockEventSource.instances).toHaveLength(1)

    unsubscribe()
  })

  it("reports browser offline and online transitions without changing the protocol", () => {
    const onConnectionChange = vi.fn()
    const unsubscribe = subscribeAgentEvents({
      sessionId: "session-1",
      onEvent: vi.fn(),
      onConnectionChange,
    })

    window.dispatchEvent(new Event("offline"))
    window.dispatchEvent(new Event("online"))

    expect(onConnectionChange).toHaveBeenCalledWith("disconnected")
    expect(onConnectionChange).toHaveBeenLastCalledWith("reconnecting")
    unsubscribe()
  })

  it("reconnects immediately when the browser returns online without leaving a stale retry", () => {
    const onConnectionChange = vi.fn()
    const unsubscribe = subscribeAgentEvents({
      sessionId: "session-1",
      onEvent: vi.fn(),
      onConnectionChange,
    })
    const failedSource = MockEventSource.instances[0]

    failedSource.error()
    window.dispatchEvent(new Event("offline"))
    vi.advanceTimersByTime(500)
    window.dispatchEvent(new Event("online"))

    expect(MockEventSource.instances).toHaveLength(2)
    expect(failedSource.closed).toBe(true)
    expect(onConnectionChange).toHaveBeenLastCalledWith("reconnecting")

    window.dispatchEvent(new Event("online"))
    vi.advanceTimersByTime(15_000)
    expect(MockEventSource.instances).toHaveLength(2)

    unsubscribe()
  })
})
