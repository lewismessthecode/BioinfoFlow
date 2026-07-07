import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { act, renderHook } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Must import the named export (useIsMobile) — useMediaQuery is not exported
import { useIsMobile } from "@/hooks/use-media-query"

type ChangeHandler = (event: MediaQueryListEvent) => void

function createMockMatchMedia(initialMatches: boolean) {
  let currentMatches = initialMatches
  const listeners = new Set<ChangeHandler>()

  const mql = {
    get matches() {
      return currentMatches
    },
    addEventListener: vi.fn((_event: string, handler: ChangeHandler) => {
      listeners.add(handler)
    }),
    removeEventListener: vi.fn((_event: string, handler: ChangeHandler) => {
      listeners.delete(handler)
    }),
  }

  function fireChange(matches: boolean) {
    currentMatches = matches
    listeners.forEach((handler) =>
      handler({ matches } as MediaQueryListEvent)
    )
  }

  return { mql, fireChange }
}

describe("useIsMobile (useMediaQuery)", () => {
  let mockMatchMedia: ReturnType<typeof createMockMatchMedia>

  beforeEach(() => {
    mockMatchMedia = createMockMatchMedia(false)
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => mockMatchMedia.mql)
    )
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("returns false on desktop-width viewports", () => {
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)
  })

  it("returns true when viewport matches mobile breakpoint", () => {
    mockMatchMedia = createMockMatchMedia(true)
    vi.stubGlobal(
      "matchMedia",
      vi.fn(() => mockMatchMedia.mql)
    )

    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(true)
  })

  it("updates when the media query match changes", () => {
    const { result } = renderHook(() => useIsMobile())
    expect(result.current).toBe(false)

    act(() => {
      mockMatchMedia.fireChange(true)
    })

    expect(result.current).toBe(true)

    act(() => {
      mockMatchMedia.fireChange(false)
    })

    expect(result.current).toBe(false)
  })

  it("cleans up the listener on unmount", () => {
    const { unmount } = renderHook(() => useIsMobile())
    unmount()

    expect(mockMatchMedia.mql.removeEventListener).toHaveBeenCalledWith(
      "change",
      expect.any(Function)
    )
  })

  it("passes the correct media query string", () => {
    renderHook(() => useIsMobile())

    expect(window.matchMedia).toHaveBeenCalledWith("(max-width: 1023px)")
  })

  it("keeps the first client render aligned with the server snapshot", () => {
    const source = readFileSync(
      resolve(process.cwd(), "hooks/use-media-query.ts"),
      "utf8",
    )

    expect(source).not.toContain("useState(getMatches)")
    expect(source).toContain("useState(false)")
  })
})
