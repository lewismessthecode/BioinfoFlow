import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useEvents } from "@/hooks/use-events"

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

  removeEventListener(eventName: string, listener: (event: MessageEvent) => void) {
    this.listeners.get(eventName)?.delete(listener)
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }

  emit(eventName: string, payload: unknown) {
    const event = {
      data: typeof payload === "string" ? payload : JSON.stringify(payload),
    } as MessageEvent
    this.listeners.get(eventName)?.forEach((listener) => listener(event))
  }
}

describe("useEvents", () => {
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

  it("connects to the filtered stream URL and forwards parsed run events", () => {
    const onRunStatus = vi.fn()
    const onOpen = vi.fn()

    const { result } = renderHook(() =>
      useEvents({
        projectId: "project-1",
        runId: "run-1",
        imageId: "image-1",
        onRunStatus,
        onOpen,
      })
    )

    expect(result.current.connectionState).toBe("connecting")
    expect(MockEventSource.instances).toHaveLength(1)

    const source = MockEventSource.instances[0]
    expect(source.url).toContain("/api/v1/events/stream")
    expect(source.url).toContain("project_id=project-1")
    expect(source.url).toContain("run_id=run-1")
    expect(source.url).toContain("image_id=image-1")
    expect(source.options).toEqual({ withCredentials: true })

    act(() => {
      source.readyState = MockEventSource.OPEN
      source.onopen?.(new Event("open"))
    })

    expect(result.current.connectionState).toBe("connected")
    expect(onOpen).toHaveBeenCalledTimes(1)

    const envelope = {
      event: "run.status",
      run_id: "run-1",
      data: { run_id: "run-1", status: "running" },
    }

    act(() => {
      source.emit("run.status", envelope)
      source.emit("run.status", "{bad-json")
    })

    expect(onRunStatus).toHaveBeenCalledTimes(1)
    expect(onRunStatus).toHaveBeenCalledWith(envelope)
  })

  it("reconnects after a closed event source error", () => {
    const onError = vi.fn()

    const { result } = renderHook(() =>
      useEvents({
        projectId: "project-1",
        onError,
      })
    )

    const firstSource = MockEventSource.instances[0]

    act(() => {
      firstSource.readyState = MockEventSource.CLOSED
      firstSource.onerror?.(new Event("error"))
    })

    expect(onError).toHaveBeenCalledTimes(1)
    expect(result.current.connectionState).toBe("reconnecting")

    act(() => {
      vi.advanceTimersByTime(1000)
    })

    expect(MockEventSource.instances).toHaveLength(2)

    const secondSource = MockEventSource.instances[1]
    act(() => {
      secondSource.readyState = MockEventSource.OPEN
      secondSource.onopen?.(new Event("open"))
    })

    expect(result.current.connectionState).toBe("connected")
  })
})
