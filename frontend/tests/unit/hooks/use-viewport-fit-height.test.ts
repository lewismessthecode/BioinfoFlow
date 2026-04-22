import { renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { useViewportFitHeight } from "@/hooks/use-viewport-fit-height"

describe("useViewportFitHeight", () => {
  const rafCallbacks: FrameRequestCallback[] = []

  beforeEach(() => {
    rafCallbacks.length = 0

    vi.stubGlobal(
      "requestAnimationFrame",
      vi.fn((cb: FrameRequestCallback) => {
        rafCallbacks.push(cb)
        return rafCallbacks.length
      })
    )
    vi.stubGlobal("cancelAnimationFrame", vi.fn())

    // Default viewport height
    Object.defineProperty(window, "innerHeight", {
      value: 900,
      writable: true,
      configurable: true,
    })
    // No visualViewport by default
    Object.defineProperty(window, "visualViewport", {
      value: null,
      writable: true,
      configurable: true,
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  it("returns a ref callback and a fallback style when no element is attached", () => {
    const { result } = renderHook(() => useViewportFitHeight())

    expect(result.current.ref).toBeTypeOf("function")
    // Before any element is measured, should return min-height fallback
    expect(result.current.style).toEqual({ minHeight: "400px" })
  })

  it("returns undefined style when disabled", () => {
    const { result } = renderHook(() =>
      useViewportFitHeight({ enabled: false })
    )

    expect(result.current.style).toBeUndefined()
  })

  it("provides a ref callback that can accept a DOM element", () => {
    const { result } = renderHook(() =>
      useViewportFitHeight({ bottomOffset: 16 })
    )

    // The ref callback should accept null without throwing
    expect(() => result.current.ref(null)).not.toThrow()
  })

  it("registers resize and scroll event listeners when enabled", () => {
    const addSpy = vi.spyOn(window, "addEventListener")

    renderHook(() => useViewportFitHeight())

    const registeredEvents = addSpy.mock.calls.map((call) => call[0])
    expect(registeredEvents).toContain("resize")
    expect(registeredEvents).toContain("scroll")
  })

  it("cleans up event listeners on unmount", () => {
    const removeSpy = vi.spyOn(window, "removeEventListener")

    const { unmount } = renderHook(() => useViewportFitHeight())
    unmount()

    const removedEvents = removeSpy.mock.calls.map((call) => call[0])
    expect(removedEvents).toContain("resize")
    expect(removedEvents).toContain("scroll")
  })
})
