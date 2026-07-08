"use client"

import { useCallback, useEffect, useRef, useState } from "react"

export function useTransientScrollbar(visibleMs = 700) {
  const [isScrolling, setIsScrolling] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof window.setTimeout> | null>(null)

  const onScroll = useCallback(() => {
    setIsScrolling(true)
    if (timeoutRef.current) {
      window.clearTimeout(timeoutRef.current)
    }
    timeoutRef.current = window.setTimeout(() => {
      setIsScrolling(false)
      timeoutRef.current = null
    }, visibleMs)
  }, [visibleMs])

  useEffect(() => {
    return () => {
      if (timeoutRef.current) {
        window.clearTimeout(timeoutRef.current)
      }
    }
  }, [])

  return {
    "data-scrolling": isScrolling ? "true" : undefined,
    onScroll,
  }
}
