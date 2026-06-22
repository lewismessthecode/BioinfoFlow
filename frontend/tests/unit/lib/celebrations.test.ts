import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  buildStageConfettiEmitters,
  celebrateMilestone,
  celebratePreview,
  isCelebrationsEnabled,
  setCelebrationsEnabled,
  subscribeToCelebrationsPreference,
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

  it("builds a stage-style emitter layout with multiple launch points near the bottom edges", () => {
    const emitters = buildStageConfettiEmitters(1440, 900)

    expect(emitters.length).toBeGreaterThanOrEqual(6)
    expect(emitters.every((emitter) => emitter.y >= 900 * 0.88)).toBe(true)
    expect(emitters.some((emitter) => emitter.x <= 1440 * 0.3)).toBe(true)
    expect(emitters.some((emitter) => emitter.x >= 1440 * 0.7)).toBe(true)
  })

  it("fires a celebration only once per milestone", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateMilestone("first-project")
    celebrateMilestone("first-project")

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

    celebrateMilestone("first-provider-key")

    expect(appendSpy).not.toHaveBeenCalled()
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-provider-key")).toBe("1")
  })

  it("defaults celebrations to enabled and notifies preference subscribers", () => {
    const listener = vi.fn()
    const unsubscribe = subscribeToCelebrationsPreference(listener)

    expect(isCelebrationsEnabled()).toBe(true)

    setCelebrationsEnabled(false)
    expect(isCelebrationsEnabled()).toBe(false)
    expect(window.localStorage.getItem("bioinfoflow:celebrations:enabled")).toBe("0")
    expect(listener).toHaveBeenCalledWith(false)

    unsubscribe()
    setCelebrationsEnabled(true)
    expect(listener).toHaveBeenCalledTimes(1)
  })

  it("records one-time milestones without animating when celebrations are disabled", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    setCelebrationsEnabled(false)
    celebrateMilestone("first-provider-key")

    expect(appendSpy).not.toHaveBeenCalled()
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-provider-key")).toBe("1")
  })

  it("coalesces near-simultaneous milestones into one quiet animation while recording each one", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateMilestone("first-project")
    celebrateMilestone("first-workflow-registered")
    celebrateMilestone("first-workflow-bound")

    expect(appendSpy).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-project")).toBe("1")
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-workflow-registered")).toBe("1")
    expect(window.localStorage.getItem("bioinfoflow:celebrated:first-workflow-bound")).toBe("1")
  })

  it("reuses a single confetti canvas for repeated preview triggers", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebratePreview()
    celebratePreview()

    expect(appendSpy).toHaveBeenCalledTimes(1)
    expect(document.body.querySelectorAll("canvas[aria-hidden='true']")).toHaveLength(1)
    expect(window.localStorage.getItem("bioinfoflow:celebrated:preview")).toBeNull()
  })

  it("stops a delayed animation frame when the canvas has been removed", () => {
    const clearRect = vi.fn()
    let frameCallback: FrameRequestCallback | null = null
    vi.stubGlobal("requestAnimationFrame", (callback: FrameRequestCallback) => {
      frameCallback = callback
      return 1
    })
    vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue({
      clearRect,
      fillRect: vi.fn(),
      restore: vi.fn(),
      rotate: vi.fn(),
      save: vi.fn(),
      scale: vi.fn(),
      translate: vi.fn(),
      fillStyle: "",
    } as unknown as CanvasRenderingContext2D)

    celebratePreview()
    document.body.innerHTML = ""

    frameCallback?.(0)

    expect(clearRect).not.toHaveBeenCalled()
  })

  it("suppresses preview confetti when reduced motion is preferred", () => {
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

    celebratePreview()

    expect(appendSpy).not.toHaveBeenCalled()
  })

  it("does not persist preview as a milestone", () => {
    celebratePreview()

    expect(window.localStorage.getItem("bioinfoflow:celebrated:preview")).toBeNull()
  })
})
