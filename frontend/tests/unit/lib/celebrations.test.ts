import { beforeEach, describe, expect, it, vi } from "vitest"

import {
  buildStageConfettiEmitters,
  celebrateOnce,
  celebratePreview,
  celebrateReadinessTransitions,
  isCelebrationsEnabled,
  readinessMilestonesFromSummary,
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

  it("derives first-run milestones from readiness summary", () => {
    expect(
      readinessMilestonesFromSummary({
        provider_key_configured: true,
        projects: 1,
        workflows: 1,
      }),
    ).toEqual(["provider-key", "first-project", "first-workflow"])
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

  it("does not animate one-time milestones when celebrations are disabled", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    setCelebrationsEnabled(false)
    celebrateOnce("provider-api-key-saved")

    expect(appendSpy).not.toHaveBeenCalled()
    expect(window.localStorage.getItem("bioinfoflow:celebrated:provider-api-key-saved")).toBeNull()
  })

  it("allows preview confetti to run repeatedly without writing milestone keys", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebratePreview()
    celebratePreview()

    expect(appendSpy).toHaveBeenCalledTimes(2)
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

  it("fires once when a readiness check transitions from incomplete to pass", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateReadinessTransitions(
      [{ id: "project", status: "fail" }],
      [{ id: "project", status: "pass" }],
    )
    celebrateReadinessTransitions(
      [{ id: "project", status: "warn" }],
      [{ id: "project", status: "pass" }],
    )

    expect(appendSpy).toHaveBeenCalledTimes(1)
    expect(window.localStorage.getItem("bioinfoflow:celebrated:readiness-check:project")).toBe("1")
  })

  it("does not fire for checks that were already complete on the previous snapshot", () => {
    const appendSpy = vi.spyOn(document.body, "appendChild")

    celebrateReadinessTransitions(
      [{ id: "docker", status: "pass" }],
      [{ id: "docker", status: "pass" }],
    )

    expect(appendSpy).not.toHaveBeenCalled()
  })
})
