"use client"

import { useCallback, useSyncExternalStore } from "react"
import { COMPACT_MEDIA_QUERY } from "@/lib/layout-breakpoints"

export function useMediaQuery(query: string): boolean {
  const subscribe = useCallback(
    (onStoreChange: () => void) => {
      if (typeof window.matchMedia !== "function") return () => {}
      const mql = window.matchMedia(query)
      mql.addEventListener("change", onStoreChange)
      return () => mql.removeEventListener("change", onStoreChange)
    },
    [query],
  )
  const getSnapshot = useCallback(() => {
    if (typeof window.matchMedia !== "function") return false
    return window.matchMedia(query).matches
  }, [query])

  return useSyncExternalStore(subscribe, getSnapshot, () => false)
}

export function useIsMobile(): boolean {
  return useMediaQuery(COMPACT_MEDIA_QUERY)
}
