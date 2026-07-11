import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { connectEventSource } from "@/lib/runtime/event-source-connection"

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

  constructor(url: string, options?: EventSourceInit) {
    this.url = url
    this.options = options
    MockEventSource.instances.push(this)
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
}

describe("connectEventSource", () => {
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

  it("creates and binds a source using caller-owned URL and credentials", () => {
    const bindSource = vi.fn()
    const onConnect = vi.fn()
    const onOpen = vi.fn()
    const dispose = connectEventSource({
      url: () => "https://example.test/events?cursor=4",
      eventSourceInit: { withCredentials: true },
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      backoffMultiplier: 2,
      shouldReconnect: () => false,
      bindSource,
      onConnect,
      onOpen,
    })
    const source = MockEventSource.instances[0]

    expect(source.url).toBe("https://example.test/events?cursor=4")
    expect(source.options).toEqual({ withCredentials: true })
    expect(onConnect).toHaveBeenCalledOnce()
    expect(bindSource).toHaveBeenCalledOnce()
    expect(bindSource).toHaveBeenCalledWith(source)

    source.open()
    expect(onOpen).toHaveBeenCalledOnce()
    expect(onOpen).toHaveBeenCalledWith(source, expect.any(Event))

    dispose()
  })

  it("reports errors and schedules at most one retry when the predicate matches", () => {
    const onError = vi.fn()
    const dispose = connectEventSource({
      url: () => "https://example.test/events",
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      backoffMultiplier: 2,
      shouldReconnect: (source) => source.readyState === EventSource.CLOSED,
      onError,
    })
    const source = MockEventSource.instances[0]

    source.error(MockEventSource.OPEN)
    expect(onError).toHaveBeenCalledOnce()
    expect(vi.getTimerCount()).toBe(0)

    source.error(MockEventSource.CLOSED)
    source.error(MockEventSource.CLOSED)
    expect(onError).toHaveBeenCalledTimes(3)
    expect(vi.getTimerCount()).toBe(1)

    vi.advanceTimersByTime(1000)
    expect(MockEventSource.instances).toHaveLength(2)

    dispose()
  })

  it("does not reconnect when onError disposes the connection", () => {
    let dispose = () => {}
    dispose = connectEventSource({
      url: () => "https://example.test/events",
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      backoffMultiplier: 2,
      shouldReconnect: () => true,
      onError: () => dispose(),
    })
    const source = MockEventSource.instances[0]

    source.error(MockEventSource.CLOSED)

    expect(source.closed).toBe(true)
    expect(vi.getTimerCount()).toBe(0)

    vi.advanceTimersByTime(30000)
    expect(MockEventSource.instances).toHaveLength(1)
  })

  it.each([
    ["retain", false],
    ["release", false],
    ["close", true],
  ] as const)("applies the %s failed-source policy", (policy, expectedClosed) => {
    const dispose = connectEventSource({
      url: () => "https://example.test/events",
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      backoffMultiplier: 2,
      shouldReconnect: () => true,
      failedSourcePolicy: policy,
    })
    const source = MockEventSource.instances[0]

    source.error()

    expect(source.closed).toBe(expectedClosed)
    dispose()
    expect(source.closed).toBe(policy === "retain" ? true : expectedClosed)
  })

  it("uses capped exponential backoff and resets it after open", () => {
    let cursor = 0
    const dispose = connectEventSource({
      url: () => `https://example.test/events?cursor=${cursor++}`,
      initialBackoffMs: 1000,
      maxBackoffMs: 3000,
      backoffMultiplier: 2,
      shouldReconnect: () => true,
      failedSourcePolicy: "close",
    })

    for (const delay of [1000, 2000, 3000, 3000]) {
      const source = MockEventSource.instances.at(-1)!
      source.error()
      vi.advanceTimersByTime(delay - 1)
      expect(MockEventSource.instances.at(-1)).toBe(source)
      vi.advanceTimersByTime(1)
    }

    const resetSource = MockEventSource.instances.at(-1)!
    resetSource.open()
    resetSource.error()
    vi.advanceTimersByTime(999)
    expect(MockEventSource.instances.at(-1)).toBe(resetSource)
    vi.advanceTimersByTime(1)

    expect(MockEventSource.instances.map((source) => source.url)).toEqual([
      "https://example.test/events?cursor=0",
      "https://example.test/events?cursor=1",
      "https://example.test/events?cursor=2",
      "https://example.test/events?cursor=3",
      "https://example.test/events?cursor=4",
      "https://example.test/events?cursor=5",
    ])

    dispose()
  })

  it("clears pending retry work and closes the retained source on disposal", () => {
    const dispose = connectEventSource({
      url: () => "https://example.test/events",
      initialBackoffMs: 1000,
      maxBackoffMs: 30000,
      backoffMultiplier: 2,
      shouldReconnect: () => true,
      failedSourcePolicy: "retain",
    })
    const source = MockEventSource.instances[0]

    source.error()
    expect(vi.getTimerCount()).toBe(1)

    dispose()

    expect(source.closed).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    vi.runAllTimers()
    expect(MockEventSource.instances).toHaveLength(1)
  })
})
