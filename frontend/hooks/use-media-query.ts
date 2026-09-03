"use client"

import { useEffect, useState } from "react"
import { COMPACT_MEDIA_QUERY } from "@/lib/layout-breakpoints"

export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(false)

  useEffect(() => {
    if (typeof window.matchMedia !== "function") return
    const mql = window.matchMedia(query)
    const handler = (e: MediaQueryListEvent) => setMatches(e.matches)
    mql.addEventListener("change", handler)
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setMatches(mql.matches)
    return () => mql.removeEventListener("change", handler)
  }, [query])

  return matches
}

export function useIsMobile(): boolean {
  return useMediaQuery(COMPACT_MEDIA_QUERY)
}
