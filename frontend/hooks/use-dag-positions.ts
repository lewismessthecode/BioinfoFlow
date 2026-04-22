"use client"

import { useCallback, useRef, useSyncExternalStore } from "react"

type PositionMap = Record<string, { x: number; y: number }>

const STORAGE_KEY_PREFIX = "dag-positions-"
const DEBOUNCE_MS = 300

function readPositions(dagId: string): PositionMap {
  try {
    const raw = localStorage.getItem(STORAGE_KEY_PREFIX + dagId)
    return raw ? JSON.parse(raw) : {}
  } catch {
    return {}
  }
}

const emptyPositions: PositionMap = {}

export function usePersistedPositions(dagId: string) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const cacheRef = useRef<{ dagId: string; value: PositionMap } | null>(null)

  // Use useSyncExternalStore to read from localStorage without setState-in-effect
  const subscribe = useCallback(() => {
    // No external subscription needed — we manually invalidate via save/clear
    return () => {}
  }, [])

  const getSnapshot = useCallback(() => {
    if (cacheRef.current?.dagId === dagId) return cacheRef.current.value
    const value = readPositions(dagId)
    cacheRef.current = { dagId, value }
    return value
  }, [dagId])

  const getServerSnapshot = useCallback(() => emptyPositions, [])

  const positions = useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot)

  const savePosition = useCallback(
    (nodeId: string, x: number, y: number) => {
      const current = readPositions(dagId)
      const next = { ...current, [nodeId]: { x, y } }
      cacheRef.current = { dagId, value: next }

      // Debounced write to localStorage
      if (timerRef.current) clearTimeout(timerRef.current)
      timerRef.current = setTimeout(() => {
        try {
          localStorage.setItem(STORAGE_KEY_PREFIX + dagId, JSON.stringify(next))
        } catch {
          // localStorage full — silently ignore
        }
      }, DEBOUNCE_MS)
    },
    [dagId]
  )

  const clearPositions = useCallback(() => {
    cacheRef.current = { dagId, value: {} }
    try {
      localStorage.removeItem(STORAGE_KEY_PREFIX + dagId)
    } catch {
      // ignore
    }
  }, [dagId])

  return { positions, savePosition, clearPositions }
}
