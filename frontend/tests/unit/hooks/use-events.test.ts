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

  removeEventListener(eventName: string, listener: (event: MessageEvent) => void) {
    this.listeners.get(eventName)?.delete(listener)
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

describe("useEvents", () => {
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

  it("stays disconnected and creates no source without a project", () => {
    const { result } = renderHook(() => useEvents({ projectId: null }))

    expect(result.current.connectionState).toBe("disconnected")
    expect(MockEventSource.instances).toHaveLength(0)
  })

  it("uses the exact filtered URL, credentials, and named event bindings", () => {
    const onRunStatus = vi.fn()
    const onRunLog = vi.fn()
    const onRunDag = vi.fn()
    const onImageProgress = vi.fn()
    const onOpen = vi.fn()

    const { result } = renderHook(() =>
      useEvents({
        projectId: "project-1",
        runId: "run-1",
        imageId: "image-1",
        onRunStatus,
        onRunLog,
        onRunDag,
        onImageProgress,
        onOpen,
      }),
    )

    expect(result.current.connectionState).toBe("connecting")
    expect(MockEventSource.instances).toHaveLength(1)

    const source = MockEventSource.instances[0]
    const url = new URL(source.url)
    expect(url.pathname).toBe("/api/v1/events/stream")
    expect(Object.fromEntries(url.searchParams)).toEqual({
      project_id: "project-1",
      run_id: "run-1",
      image_id: "image-1",
    })
    expect(source.options).toEqual({ withCredentials: true })

    act(() => source.open())

    expect(result.current.connectionState).toBe("connected")
    expect(onOpen).toHaveBeenCalledTimes(1)

    const envelopes = {
      "run.status": { event: "run.status", data: { status: "running" } },
      "run.log": { event: "run.log", data: { line: "hello" } },
      "run.dag": { event: "run.dag", data: { nodes: [] } },
      "image.progress": { event: "image.progress", data: { progress: 50 } },
    }

    act(() => {
      source.emit("run.status", envelopes["run.status"])
      source.emit("run.log", envelopes["run.log"])
      source.emit("run.dag", envelopes["run.dag"])
      source.emit("image.progress", envelopes["image.progress"])
      source.emit("run.status", "{bad-json")
    })

    expect(onRunStatus).toHaveBeenCalledOnce()
    expect(onRunStatus).toHaveBeenCalledWith(envelopes["run.status"])
    expect(onRunLog).toHaveBeenCalledWith(envelopes["run.log"])
    expect(onRunDag).toHaveBeenCalledWith(envelopes["run.dag"])
    expect(onImageProgress).toHaveBeenCalledWith(envelopes["image.progress"])
    expect(source.onmessage).toBeNull()
  })

  it("reports every error but reconnects only for CLOSED sources", () => {
    const onError = vi.fn()
    const { result } = renderHook(() =>
      useEvents({ projectId: "project-1", onError }),
    )
    const source = MockEventSource.instances[0]

    act(() => {
      source.open()
      source.error(MockEventSource.OPEN)
    })

    expect(onError).toHaveBeenCalledOnce()
    expect(result.current.connectionState).toBe("reconnecting")
    expect(vi.getTimerCount()).toBe(0)

    act(() => source.error(MockEventSource.CLOSED))

    expect(onError).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(1)
  })

  it("keeps one timer, does not close the old source, and uses capped backoff", () => {
    const { unmount } = renderHook(() => useEvents({ projectId: "project-1" }))
    const expectedDelays = [1000, 2000, 4000, 8000, 16000, 30000, 30000]

    for (const delay of expectedDelays) {
      const source = MockEventSource.instances.at(-1)!
      act(() => {
        source.error(MockEventSource.CLOSED)
        source.error(MockEventSource.CLOSED)
      })

      expect(vi.getTimerCount()).toBe(1)
      act(() => vi.advanceTimersByTime(delay - 1))
      expect(MockEventSource.instances.at(-1)).toBe(source)
      act(() => vi.advanceTimersByTime(1))
      expect(source.closed).toBe(false)
    }

    expect(MockEventSource.instances).toHaveLength(expectedDelays.length + 1)
    unmount()
  })

  it("resets backoff on open and clears retry work on cleanup", () => {
    const { unmount } = renderHook(() => useEvents({ projectId: "project-1" }))
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
    expect(MockEventSource.instances).toHaveLength(4)

    const fourthSource = MockEventSource.instances[3]
    act(() => fourthSource.error(MockEventSource.CLOSED))
    expect(vi.getTimerCount()).toBe(1)

    unmount()

    expect(fourthSource.closed).toBe(true)
    expect(vi.getTimerCount()).toBe(0)
    act(() => vi.runAllTimers())
    expect(MockEventSource.instances).toHaveLength(4)
  })
})
