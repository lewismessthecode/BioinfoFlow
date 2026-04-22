import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { usePersistedPositions } from "@/hooks/use-dag-positions"

describe("usePersistedPositions", () => {
  beforeEach(() => {
    vi.useFakeTimers()
    localStorage.clear()
  })

  afterEach(() => {
    vi.runOnlyPendingTimers()
    vi.useRealTimers()
  })

  it("returns empty positions for a new DAG id", () => {
    const { result } = renderHook(() => usePersistedPositions("dag-1"))
    expect(result.current.positions).toEqual({})
  })

  it("reads existing positions from localStorage", () => {
    const stored = { nodeA: { x: 100, y: 200 }, nodeB: { x: 300, y: 400 } }
    localStorage.setItem("dag-positions-dag-2", JSON.stringify(stored))

    const { result } = renderHook(() => usePersistedPositions("dag-2"))
    expect(result.current.positions).toEqual(stored)
  })

  it("saves a position and writes to localStorage after debounce", () => {
    const { result } = renderHook(() => usePersistedPositions("dag-3"))

    act(() => {
      result.current.savePosition("node1", 50, 75)
    })

    // Before debounce fires, localStorage should still be empty
    expect(localStorage.getItem("dag-positions-dag-3")).toBeNull()

    // After debounce (300ms), localStorage should be updated
    act(() => {
      vi.advanceTimersByTime(300)
    })

    const saved = JSON.parse(localStorage.getItem("dag-positions-dag-3")!)
    expect(saved).toEqual({ node1: { x: 50, y: 75 } })
  })

  it("clears positions from both cache and localStorage", () => {
    localStorage.setItem(
      "dag-positions-dag-4",
      JSON.stringify({ n: { x: 1, y: 2 } })
    )

    const { result } = renderHook(() => usePersistedPositions("dag-4"))
    expect(result.current.positions).toEqual({ n: { x: 1, y: 2 } })

    act(() => {
      result.current.clearPositions()
    })

    expect(localStorage.getItem("dag-positions-dag-4")).toBeNull()
  })

  it("handles corrupt JSON in localStorage gracefully", () => {
    localStorage.setItem("dag-positions-dag-5", "not-valid-json")

    const { result } = renderHook(() => usePersistedPositions("dag-5"))
    expect(result.current.positions).toEqual({})
  })
})
