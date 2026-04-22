"use client"

import { useCallback, useEffect, useRef, useState } from "react"

interface UseViewportFitHeightOptions {
  bottomOffset?: number
  enabled?: boolean
}

export function useViewportFitHeight<T extends HTMLElement>({
  bottomOffset = 24,
  enabled = true,
}: UseViewportFitHeightOptions = {}) {
  const elementRef = useRef<T | null>(null)
  const [height, setHeight] = useState<number | null>(null)

  const measure = useCallback(() => {
    if (!enabled || !elementRef.current || typeof window === "undefined") return

    // Skip measurement when element is hidden (e.g. inactive tab)
    if (elementRef.current.offsetParent === null) return

    const viewportHeight = window.visualViewport?.height ?? window.innerHeight
    const top = elementRef.current.getBoundingClientRect().top
    const availableHeight = Math.floor(viewportHeight - top - bottomOffset)

    if (!Number.isFinite(availableHeight) || availableHeight <= 0) return

    setHeight((current) =>
      current === availableHeight ? current : availableHeight
    )
  }, [bottomOffset, enabled])

  const observerRef = useRef<MutationObserver | null>(null)

  const ref = useCallback(
    (node: T | null) => {
      // Clean up previous observer
      observerRef.current?.disconnect()
      observerRef.current = null

      elementRef.current = node
      if (!enabled || !node || typeof window === "undefined") return
      window.requestAnimationFrame(measure)

      // Observe parent tab for visibility changes (e.g. Radix TabsContent data-state)
      const parent = node.closest("[data-state]")
      if (parent) {
        const obs = new MutationObserver(() =>
          window.requestAnimationFrame(measure)
        )
        obs.observe(parent, { attributes: true, attributeFilter: ["data-state", "hidden"] })
        observerRef.current = obs
      }
    },
    [enabled, measure]
  )

  useEffect(() => {
    if (!enabled) return

    let frameId = window.requestAnimationFrame(measure)
    const scheduleMeasure = () => {
      window.cancelAnimationFrame(frameId)
      frameId = window.requestAnimationFrame(measure)
    }

    window.addEventListener("resize", scheduleMeasure)
    window.addEventListener("scroll", scheduleMeasure, true)
    window.visualViewport?.addEventListener("resize", scheduleMeasure)
    window.visualViewport?.addEventListener("scroll", scheduleMeasure)

    return () => {
      window.cancelAnimationFrame(frameId)
      window.removeEventListener("resize", scheduleMeasure)
      window.removeEventListener("scroll", scheduleMeasure, true)
      window.visualViewport?.removeEventListener("resize", scheduleMeasure)
      window.visualViewport?.removeEventListener("scroll", scheduleMeasure)
      observerRef.current?.disconnect()
    }
  }, [enabled, measure])

  return {
    ref,
    style: enabled
      ? height !== null
        ? { height: `${height}px` }
        : { minHeight: "400px" }
      : undefined,
  }
}
