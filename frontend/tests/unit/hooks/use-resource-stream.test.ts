import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { useResourceStream } from "@/hooks/use-resource-stream"
import type { ResourceStreamFrame } from "@/lib/types"

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

  emit(eventName: string, payload: unknown) {
    const event = {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent
    this.listeners.get(eventName)?.forEach((listener) => listener(event))
  }
}

function frame(activeRunIds: string[] = []): ResourceStreamFrame {
  return {
    mode: "local",
    effective_mode: "local",
    scheduler_available: true,
    resources: {
      enabled: true,
      sampled_at: "2026-07-11T00:00:00Z",
      cpu: { total: 8, available: 6 },
      memory: { total_gb: 32, available_gb: 20 },
      disk: { total_gb: 100, available_gb: 60 },
      gpu: { count: 1, memory_gb: 12 },
    },
    active_runs: activeRunIds.map((runId) => ({
      run_id: runId,
      weight: 1,
      workflow_name: null,
    })),
    queue_depth: 0,
  }
}

describe("useResourceStream", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date("2026-07-11T00:00:00Z"))
    MockEventSource.instances = []
    vi.stubGlobal("EventSource", MockEventSource)
  })

  afterEach(() => {
    vi.clearAllTimers()
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it("stays disconnected without creating a source when disabled", () => {
    const { result } = renderHook(() => useResourceStream({ enabled: false }))

    expect(result.current.connectionState).toBe("disconnected")
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it("uses the exact uncredentialed URL and scheduler.resources binding", () => {
    const { result } = renderHook(() => useResourceStream({ maxSamples: 2 }))
    const source = MockEventSource.instances[0]
    const url = new URL(source.url)

    expect(result.current.connectionState).toBe("connecting")
    expect(url.pathname).toBe("/api/v1/scheduler/resources/stream")
    expect(url.search).toBe("")
    expect(source.options).toBeUndefined()
    expect(source.onmessage).toBeNull()

    act(() => source.open())
    expect(result.current.connectionState).toBe("connected")

    act(() => {
      source.emit("scheduler.resources", frame(["run-1"]))
      source.emit("scheduler.resources", "{bad-json")
    })

    expect(result.current.frame).toEqual(frame(["run-1"]))
    expect(result.current.samples).toEqual([
      {
        t: 1783728000,
        cpu: 25,
        memUsedGb: 12,
        memTotalGb: 32,
        diskUsedGb: 40,
        diskTotalGb: 100,
        gpuFreeGb: 12,
        gpuCount: 1,
        cpuCores: 8,
        cpuAvailable: 6,
      },
    ])
    expect(result.current.events).toEqual([
      { t: 1783728000, kind: "dispatch", run_id: "run-1" },
    ])

    act(() => {
      vi.setSystemTime(new Date("2026-07-11T00:00:01Z"))
      source.emit("scheduler.resources", frame([]))
      vi.setSystemTime(new Date("2026-07-11T00:00:02Z"))
      source.emit("scheduler.resources", frame([]))
    })

    expect(result.current.samples).toHaveLength(2)
    expect(result.current.events.at(-1)).toEqual({
      t: 1783728001,
      kind: "complete",
      run_id: "run-1",
    })
  })

  it("reconnects only after CLOSED errors and releases without closing the source", () => {
    const { result, unmount } = renderHook(() => useResourceStream())
    const firstSource = MockEventSource.instances[0]

    act(() => {
      firstSource.open()
      firstSource.error(MockEventSource.OPEN)
    })

    expect(result.current.connectionState).toBe("connected")
    expect(vi.getTimerCount()).toBe(0)

    act(() => {
      firstSource.error(MockEventSource.CLOSED)
      firstSource.error(MockEventSource.CLOSED)
    })

    expect(result.current.connectionState).toBe("reconnecting")
    expect(firstSource.closed).toBe(false)
    expect(vi.getTimerCount()).toBe(1)

    unmount()

    expect(firstSource.closed).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })

  it("uses a 30 second capped backoff without closing replaced sources", () => {
    const { unmount } = renderHook(() => useResourceStream())
    const expectedDelays = [1000, 2000, 4000, 8000, 16000, 30000, 30000]

    for (const delay of expectedDelays) {
      const source = MockEventSource.instances.at(-1)!
      act(() => source.error(MockEventSource.CLOSED))
      act(() => vi.advanceTimersByTime(delay - 1))
      expect(MockEventSource.instances.at(-1)).toBe(source)
      act(() => vi.advanceTimersByTime(1))
      expect(source.closed).toBe(false)
    }

    expect(MockEventSource.instances).toHaveLength(expectedDelays.length + 1)
    unmount()
  })

  it("resets backoff on open and closes only the active source on cleanup", () => {
    const { result, unmount } = renderHook(() => useResourceStream())
    const firstSource = MockEventSource.instances[0]

    act(() => {
      firstSource.error(MockEventSource.CLOSED)
      vi.advanceTimersByTime(1000)
    })
    const secondSource = MockEventSource.instances[1]
    act(() => {
      secondSource.error(MockEventSource.CLOSED)
      vi.advanceTimersByTime(2000)
    })
    const thirdSource = MockEventSource.instances[2]
    act(() => {
      thirdSource.open()
      thirdSource.error(MockEventSource.CLOSED)
      vi.advanceTimersByTime(999)
    })
    expect(MockEventSource.instances).toHaveLength(3)

    act(() => vi.advanceTimersByTime(1))
    const fourthSource = MockEventSource.instances[3]
    act(() => fourthSource.open())
    expect(result.current.connectionState).toBe("connected")

    unmount()

    expect(firstSource.closed).toBe(false)
    expect(secondSource.closed).toBe(false)
    expect(thirdSource.closed).toBe(false)
    expect(fourthSource.closed).toBe(true)
    expect(result.current.connectionState).toBe("connected")
    expect(vi.getTimerCount()).toBe(0)
  })
})
