"use client"

import { useEffect, useState, useSyncExternalStore } from "react"

const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)"
const TYPE_DELAY_MS = 80
const COMPLETE_PAUSE_MS = 1_400
const DELETE_DELAY_MS = 35
const NEXT_PLACEHOLDER_DELAY_MS = 300

type PlaceholderPhase = "typing" | "pausing" | "deleting"

type AnimatedPlaceholderState = {
  index: number
  phase: PlaceholderPhase
  text: string
}

type UseAnimatedPlaceholderOptions = {
  enabled: boolean
  focused: boolean
  value: string
  strings: readonly string[]
}

export function useAnimatedPlaceholder({
  enabled,
  focused,
  value,
  strings,
}: UseAnimatedPlaceholderOptions): string {
  const reducedMotion = useReducedMotionPreference()
  const [state, setState] = useState<AnimatedPlaceholderState>({
    index: 0,
    phase: "typing",
    text: "",
  })
  const shouldAnimate =
    enabled && !focused && value.length === 0 && !reducedMotion && strings.length > 0

  useEffect(() => {
    if (!shouldAnimate) return

    const current = strings[state.index % strings.length] ?? ""
    let timer: ReturnType<typeof setTimeout>

    if (state.phase === "typing") {
      timer = window.setTimeout(() => {
        setState((previous) => {
          const text = current.slice(0, previous.text.length + 1)
          return {
            ...previous,
            phase: text === current ? "pausing" : "typing",
            text,
          }
        })
      }, TYPE_DELAY_MS)
    } else if (state.phase === "pausing") {
      timer = window.setTimeout(() => {
        setState((previous) => ({ ...previous, phase: "deleting" }))
      }, COMPLETE_PAUSE_MS)
    } else if (state.text.length > 0) {
      timer = window.setTimeout(() => {
        setState((previous) => ({
          ...previous,
          text: previous.text.slice(0, -1),
        }))
      }, DELETE_DELAY_MS)
    } else {
      timer = window.setTimeout(() => {
        setState((previous) => ({
          index: (previous.index + 1) % strings.length,
          phase: "typing",
          text: "",
        }))
      }, NEXT_PLACEHOLDER_DELAY_MS)
    }

    return () => window.clearTimeout(timer)
  }, [shouldAnimate, state, strings])

  if (!shouldAnimate) return strings[0] ?? ""
  return state.text
}

function useReducedMotionPreference(): boolean {
  return useSyncExternalStore(
    subscribeToReducedMotionPreference,
    readReducedMotionPreference,
    () => false,
  )
}

function readReducedMotionPreference(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return false
  }
  return window.matchMedia(REDUCED_MOTION_QUERY).matches
}

function subscribeToReducedMotionPreference(onChange: () => void): () => void {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
    return () => {}
  }

  const mediaQuery = window.matchMedia(REDUCED_MOTION_QUERY)
  if (typeof mediaQuery.addEventListener === "function") {
    mediaQuery.addEventListener("change", onChange)
    return () => mediaQuery.removeEventListener("change", onChange)
  }

  mediaQuery.addListener(onChange)
  return () => mediaQuery.removeListener(onChange)
}
