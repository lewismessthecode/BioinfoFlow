import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  celebrateOnce,
  readinessMilestonesFromSummary,
} from "@/lib/celebrations"

describe("celebrations", () => {
  beforeEach(() => {
    vi.restoreAllMocks()
    vi.unstubAllGlobals()
    window.localStorage.clear()
    document.body.innerHTML = ""
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      setTimeout(() => callback(0), 0)
      return 1
    })
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect: vi.fn(),
      fillRect: vi.fn(),
      restore: vi.fn(),
      rotate: vi.fn(),
      save: vi.fn(),
      scale: vi.fn(),
      translate: vi.fn(),
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D)
  })

  it("derives first-run milestones from readiness summary", () => {
    expect(
      readinessMilestonesFromSummary({
        provider_key_configured: true,
        projects: 1,
        workflows: 1,
      }),
    ).toEqual(["provider-key", "first-project", "first-workflow"])
  })

  it("fires a celebration only once per milestone", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateOnce("first-project")
    celebrateOnce("first-project")

    expect(appendSpy).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-project")).toBe(
      "1",
    )
  })

  it("does not animate when reduced motion is preferred", () => {
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: true,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateOnce("provider-key")

    expect(appendSpy).not.toHaveBeenCalled()
    expect(window.localStorage.getItem("bioinfoflow:celebrated:provider-key")).toBe(
      "1",
    )
  })

  it("stops safely when the animation frame runs after window teardown", () => {
    const frames: FrameRequestCallback[] = []
    vi.stubGlobal("requestAnimationFrame", vi.fn((callback: FrameRequestCallback) => {
      frames.push(callback)
      return frames.length
    }))

    celebrateOnce("first-workflow")
    vi.stubGlobal("window", undefined)

    expect(() => frames[0]?.(0)).not.toThrow()
  })
})
