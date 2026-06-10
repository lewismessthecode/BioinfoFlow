"use client"

import { useSyncExternalStore } from "react"

export type CelebrationMilestone =
  | "provider-key"
  | "first-project"
  | "first-workflow"
  | "provider-api-key-saved"
  | "first-workflow-registered"
  | "first-workflow-bound-to-project"

type ReadinessSummary = {
  provider_key_configured?: boolean
  projects?: number
  workflows?: number
}

type ReadinessCelebrationCheck = {
  id: string
  status: "pass" | "fail" | "warn" | "skip"
}

type StageConfettiEmitter = {
  x: number
  y: number
  count: number
  delayFrames: number
  velocityX: readonly [number, number]
  velocityY: readonly [number, number]
  drift: number
}

const STORAGE_PREFIX = "bioinfoflow:celebrated:"
const CELEBRATIONS_ENABLED_KEY = "bioinfoflow:celebrations:enabled"
const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"
const COLORS = ["#15b8a6", "#f4b740", "#ec5b56", "#5c8df6", "#f7f3e8"]
const celebrationPreferenceSubscribers = new Set<(enabled: boolean) => void>()

export function readinessMilestonesFromSummary(
  summary?: ReadinessSummary | null,
): CelebrationMilestone[] {
  if (!summary) {
    return []
  }

  const milestones: CelebrationMilestone[] = []
  if (summary.provider_key_configured) {
    milestones.push("provider-key")
  }
  if ((summary.projects ?? 0) > 0) {
    milestones.push("first-project")
  }
  if ((summary.workflows ?? 0) > 0) {
    milestones.push("first-workflow")
  }
  return milestones
}

export function celebrateReadinessTransitions(
  previousChecks: ReadonlyArray<ReadinessCelebrationCheck> | null | undefined,
  nextChecks: ReadonlyArray<ReadinessCelebrationCheck>,
): void {
  if (!previousChecks) {
    return
  }

  const previousStatus = new Map(
    previousChecks.map((check) => [check.id, check.status]),
  )

  for (const check of nextChecks) {
    if (check.status !== "pass") {
      continue
    }

    const before = previousStatus.get(check.id)
    if (before && before !== "pass") {
      celebrateOnce(`readiness-check:${check.id}`)
    }
  }
}

export function isCelebrationsEnabled(): boolean {
  if (typeof window === "undefined") {
    return true
  }

  return window.localStorage.getItem(CELEBRATIONS_ENABLED_KEY) !== "0"
}

export function setCelebrationsEnabled(enabled: boolean): void {
  if (typeof window === "undefined") {
    return
  }

  window.localStorage.setItem(CELEBRATIONS_ENABLED_KEY, enabled ? "1" : "0")
  for (const subscriber of celebrationPreferenceSubscribers) {
    subscriber(enabled)
  }
}

export function subscribeToCelebrationsPreference(
  callback: (enabled: boolean) => void,
): () => void {
  celebrationPreferenceSubscribers.add(callback)
  return () => {
    celebrationPreferenceSubscribers.delete(callback)
  }
}

export function useCelebrationsEnabledPreference(): boolean {
  return useSyncExternalStore(
    subscribeToCelebrationsStore,
    isCelebrationsEnabled,
    () => true,
  )
}

export function isReducedMotionPreferred(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false
  }

  return window.matchMedia(REDUCED_MOTION_QUERY).matches
}

export function useReducedMotionPreference(): boolean {
  return useSyncExternalStore(
    subscribeToReducedMotionPreference,
    isReducedMotionPreferred,
    () => false,
  )
}

export function celebrateOnce(
  milestone: CelebrationMilestone | `readiness-check:${string}`,
): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return false
  }

  if (!isCelebrationsEnabled()) {
    return false
  }

  const key = `${STORAGE_PREFIX}${milestone}`
  if (window.localStorage.getItem(key) === "1") {
    return false
  }

  window.localStorage.setItem(key, "1")

  if (isReducedMotionPreferred()) {
    return true
  }

  launchCanvasConfetti()
  return true
}

export function celebratePreview(): boolean {
  if (typeof window === "undefined" || typeof document === "undefined") {
    return false
  }

  if (!isCelebrationsEnabled() || isReducedMotionPreferred()) {
    return false
  }

  launchCanvasConfetti()
  return true
}

export function buildStageConfettiEmitters(
  width: number,
  height: number,
): StageConfettiEmitter[] {
  const stageY = height * 0.955
  const leftBand = [0.12, 0.16, 0.22, 0.28]
  const rightBand = [0.72, 0.78, 0.84, 0.88]

  const buildBand = (
    band: number[],
    direction: "left" | "right",
  ): StageConfettiEmitter[] =>
    band.map((ratio, index) => {
      const outward = direction === "left" ? 1 : -1
      const horizontalMin = outward * (2.8 + index * 0.45)
      const horizontalMax = outward * (6.4 + index * 0.65)

      return {
        x: width * ratio,
        y: stageY + height * ((index % 2) * 0.006),
        count: index < 2 ? 24 : 28,
        delayFrames: index * 4,
        velocityX:
          direction === "left"
            ? [horizontalMin, horizontalMax]
            : [horizontalMax, horizontalMin],
        velocityY: [-14.4 + index * 0.35, -8.8 + index * 0.2],
        drift: outward * (0.05 + index * 0.018),
      }
    })

  return [...buildBand(leftBand, "left"), ...buildBand(rightBand, "right")]
}

function launchCanvasConfetti() {
  const canvas = document.createElement("canvas")
  canvas.setAttribute("aria-hidden", "true")
  canvas.style.position = "fixed"
  canvas.style.inset = "0"
  canvas.style.width = "100vw"
  canvas.style.height = "100vh"
  canvas.style.pointerEvents = "none"
  canvas.style.zIndex = "2147483647"
  document.body.appendChild(canvas)

  const context = canvas.getContext("2d")
  if (!context) {
    canvas.remove()
    return
  }

  const viewportWidth = window.innerWidth
  const viewportHeight = window.innerHeight
  const scheduleFrame = window.requestAnimationFrame.bind(window)
  const scale = window.devicePixelRatio || 1
  canvas.width = Math.floor(viewportWidth * scale)
  canvas.height = Math.floor(viewportHeight * scale)
  context.scale(scale, scale)

  const emitters = buildStageConfettiEmitters(
    viewportWidth,
    viewportHeight,
  )

  const particles = emitters.flatMap((emitter, emitterIndex) =>
    Array.from({ length: emitter.count }, (_, particleIndex) => ({
      x: emitter.x,
      y: emitter.y,
      delayFrames: emitter.delayFrames + Math.floor(particleIndex / 6),
      vx:
        emitter.velocityX[0] +
        Math.random() * (emitter.velocityX[1] - emitter.velocityX[0]),
      vy:
        emitter.velocityY[0] +
        Math.random() * (emitter.velocityY[1] - emitter.velocityY[0]),
      gravity: 0.15 + Math.random() * 0.04,
      drift: emitter.drift + (Math.random() - 0.5) * 0.09,
      drag: 0.995 - Math.random() * 0.003,
      size: 6 + Math.random() * 8.5,
      height: 3.5 + Math.random() * 4.8,
      rotation: Math.random() * Math.PI,
      rotationVelocity: 0.08 + Math.random() * 0.16,
      opacity: 0.96,
      color: COLORS[(emitterIndex * 3 + particleIndex) % COLORS.length],
    })),
  )

  let frame = 0
  const maxFrames = 176

  function draw() {
    if (!canvas.isConnected) {
      return
    }

    frame += 1
    context.clearRect(0, 0, viewportWidth, viewportHeight)

    for (const particle of particles) {
      if (frame < particle.delayFrames) {
        continue
      }

      particle.vx *= particle.drag
      particle.x += particle.vx + particle.drift
      particle.y += particle.vy
      particle.vy += particle.gravity
      particle.rotation += particle.rotationVelocity
      particle.opacity = Math.max(0, particle.opacity - 0.0038)

      context.save()
      context.translate(particle.x, particle.y)
      context.rotate(particle.rotation)
      context.globalAlpha = particle.opacity
      context.fillStyle = particle.color
      context.fillRect(
        -particle.size / 2,
        -particle.height / 2,
        particle.size,
        particle.height,
      )
      context.restore()
    }

    if (frame < maxFrames) {
      scheduleFrame(draw)
      return
    }

    canvas.remove()
  }

  scheduleFrame(draw)
}

function subscribeToCelebrationsStore(callback: () => void): () => void {
  if (typeof window !== "undefined") {
    const handleStorage = (event: StorageEvent) => {
      if (event.key === CELEBRATIONS_ENABLED_KEY) {
        callback()
      }
    }
    window.addEventListener("storage", handleStorage)
    const unsubscribe = subscribeToCelebrationsPreference(() => callback())
    return () => {
      window.removeEventListener("storage", handleStorage)
      unsubscribe()
    }
  }

  return subscribeToCelebrationsPreference(() => callback())
}

function subscribeToReducedMotionPreference(callback: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {}
  }

  const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY)
  const handleChange = () => callback()

  mediaQuery.addEventListener?.("change", handleChange)
  mediaQuery.addListener?.(handleChange)

  return () => {
    mediaQuery.removeEventListener?.("change", handleChange)
    mediaQuery.removeListener?.(handleChange)
  }
}
