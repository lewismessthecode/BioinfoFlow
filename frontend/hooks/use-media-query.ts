"use client"

import { useCallback, useEffect, useState } from "react"

function useMediaQuery(query: string): boolean {
  const getMatches = useCallback(() => {
    if (typeof window === "undefined") return false
    return window.matchMedia(query).matches
  }, [query])

  const [matches, setMatches] = useState(getMatches)

  useEffect(() => {
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
  return useMediaQuery("(max-width: 1023px)")
}
