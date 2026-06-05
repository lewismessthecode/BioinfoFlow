"use client"

const readinessRefreshEvent = "bioinfoflow:readiness-refresh"

export function emitReadinessRefresh(reason?: string) {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent(readinessRefreshEvent, {
      detail: { reason: reason ?? "workspace-action" },
    }),
  )
}

export function listenForReadinessRefresh(listener: () => void) {
  if (typeof window === "undefined") return () => undefined

  const handleEvent = () => listener()
  window.addEventListener(readinessRefreshEvent, handleEvent)
  return () => {
    window.removeEventListener(readinessRefreshEvent, handleEvent)
  }
}
