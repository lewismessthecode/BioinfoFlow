import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { subscribeAgentRuntimeEvents } from "@/lib/agent-runtime"

class MockEventSource {
  static instances: MockEventSource[] = []

  readonly url: string
  readonly options?: EventSourceInit
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
  }
}

describe("subscribeAgentRuntimeEvents", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    MockEventSource.instances = []
    vi.stubGlobal("EventSource", MockEventSource)
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("closes the failed EventSource before reconnecting", () => {
    const unsubscribe = subscribeAgentRuntimeEvents({
      sessionId: "session-1",
      afterSeq: 4,
      onEvent: vi.fn(),
    })
    const firstSource = MockEventSource.instances[0]

    firstSource.onerror?.(new Event("error"))
    vi.advanceTimersByTime(1000)

    expect(firstSource.closed).toBe(true)
    expect(MockEventSource.instances).toHaveLength(2)
    expect(MockEventSource.instances[1]?.url).toContain("after_seq=4")

    unsubscribe()
  })
})
