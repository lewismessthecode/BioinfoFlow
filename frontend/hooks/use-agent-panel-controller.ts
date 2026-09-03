"use client"

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"
import type { LiveDeckTab } from "@/components/bioinfoflow/live-deck"
import type { AgentActionId } from "@/components/bioinfoflow/agent-action-group"

export const RIGHT_SIDEBAR_MIN = 300
export const RIGHT_SIDEBAR_MAX = 600
const RIGHT_SIDEBAR_DEFAULT = 400

export type AgentPanelPreferences = {
  activeTab: LiveDeckTab
  open: boolean
  width: number
}

const DEFAULT_PANEL_PREFERENCES: AgentPanelPreferences = {
  activeTab: "workspace",
  open: false,
  width: RIGHT_SIDEBAR_DEFAULT,
}
const panelPreferenceListeners = new Map<string, Set<() => void>>()

function clampRightSidebarWidth(value: number) {
  if (!Number.isFinite(value)) return RIGHT_SIDEBAR_DEFAULT
  return Math.min(RIGHT_SIDEBAR_MAX, Math.max(RIGHT_SIDEBAR_MIN, value))
}

function panelPreferenceKey(
  projectId: string | null,
  sessionId: string | null,
): string | null {
  return projectId
    ? `agent-panel:${projectId}:${sessionId || "draft"}`
    : null
}

function readPanelPreferences(key: string | null): string | null {
  if (!key || typeof window === "undefined") return null
  return window.localStorage.getItem(key)
}

function subscribeToPanelPreferences(
  key: string | null,
  listener: () => void,
): () => void {
  if (!key || typeof window === "undefined") return () => {}
  const listeners = panelPreferenceListeners.get(key) ?? new Set()
  listeners.add(listener)
  panelPreferenceListeners.set(key, listeners)
  const handleStorage = (event: StorageEvent) => {
    if (event.key === key) listener()
  }
  window.addEventListener("storage", handleStorage)
  return () => {
    listeners.delete(listener)
    window.removeEventListener("storage", handleStorage)
    if (listeners.size === 0) panelPreferenceListeners.delete(key)
  }
}

function parsePanelPreferences(raw: string | null): AgentPanelPreferences {
  if (!raw) return DEFAULT_PANEL_PREFERENCES
  try {
    const parsed = JSON.parse(raw) as Partial<AgentPanelPreferences>
    return {
      activeTab:
        parsed.activeTab === "workspace" ||
        parsed.activeTab === "dag" ||
        parsed.activeTab === "artifacts" ||
        parsed.activeTab === "browser"
          ? parsed.activeTab
          : DEFAULT_PANEL_PREFERENCES.activeTab,
      open:
        typeof parsed.open === "boolean"
          ? parsed.open
          : DEFAULT_PANEL_PREFERENCES.open,
      width:
        typeof parsed.width === "number"
          ? clampRightSidebarWidth(parsed.width)
          : DEFAULT_PANEL_PREFERENCES.width,
    }
  } catch {
    return DEFAULT_PANEL_PREFERENCES
  }
}

function writePanelPreferences(
  key: string | null,
  updates: Partial<AgentPanelPreferences>,
) {
  if (!key || typeof window === "undefined") return
  const current = parsePanelPreferences(readPanelPreferences(key))
  window.localStorage.setItem(key, JSON.stringify({ ...current, ...updates }))
  panelPreferenceListeners.get(key)?.forEach((listener) => listener())
}

function mobilePreferenceKey(key: string | null) {
  return key ? `${key}:mobile-open` : null
}

function writeMobileOpenPreference(key: string | null, open: boolean) {
  const mobileKey = mobilePreferenceKey(key)
  if (!mobileKey || typeof window === "undefined") return
  window.localStorage.setItem(mobileKey, String(open))
  panelPreferenceListeners.get(mobileKey)?.forEach((listener) => listener())
}

function migratePanelPreferences(
  projectId: string | null,
  fromSessionId: string | null,
  toSessionId: string | null,
) {
  const sourceKey = panelPreferenceKey(projectId, fromSessionId)
  const targetKey = panelPreferenceKey(projectId, toSessionId)
  if (!sourceKey || !targetKey || sourceKey === targetKey) return
  const source = readPanelPreferences(sourceKey)
  if (!source || readPanelPreferences(targetKey)) return
  window.localStorage.setItem(targetKey, source)
  window.localStorage.removeItem(sourceKey)
  panelPreferenceListeners.get(targetKey)?.forEach((listener) => listener())
  panelPreferenceListeners.get(sourceKey)?.forEach((listener) => listener())
}

const getServerPanelPreferences = () => null

const ACTION_BY_TAB: Partial<Record<LiveDeckTab, AgentActionId>> = {
  browser: "browser",
  workspace: "files",
  artifacts: "artifacts",
  dag: "dag",
}

type FocusReturn = {
  element: HTMLElement | null
  actionId: AgentActionId | null
}

export function useAgentPanelController({
  projectId,
  routeSessionId,
  isMobile,
  railRef,
}: {
  projectId: string | null
  routeSessionId: string | null
  isMobile: boolean
  railRef: React.RefObject<HTMLDivElement | null>
}) {
  const [resolvedPanelSessionId, setPanelSessionId] = useState("draft")
  const panelSessionId = routeSessionId ?? resolvedPanelSessionId
  const key = panelPreferenceKey(projectId, panelSessionId)
  const subscribe = useCallback(
    (listener: () => void) => subscribeToPanelPreferences(key, listener),
    [key],
  )
  const getSnapshot = useCallback(() => readPanelPreferences(key), [key])
  const panelSnapshot = useSyncExternalStore(
    subscribe,
    getSnapshot,
    getServerPanelPreferences,
  )
  const preferences = parsePanelPreferences(panelSnapshot)
  const mobileKey = mobilePreferenceKey(key)
  const subscribeMobile = useCallback(
    (listener: () => void) => subscribeToPanelPreferences(mobileKey, listener),
    [mobileKey],
  )
  const getMobileSnapshot = useCallback(
    () => readPanelPreferences(mobileKey),
    [mobileKey],
  )
  const mobileSnapshot = useSyncExternalStore(
    subscribeMobile,
    getMobileSnapshot,
    getServerPanelPreferences,
  )
  const mobileOpen =
    mobileSnapshot === null ? preferences.open : mobileSnapshot === "true"
  const setMobileOpen = useCallback(
    (open: boolean) => writeMobileOpenPreference(key, open),
    [key],
  )
  const update = useCallback(
    (updates: Partial<AgentPanelPreferences>) => writePanelPreferences(key, updates),
    [key],
  )
  const handoffDraftToSession = useCallback(
    (sessionId: string, sessionProjectId = projectId) => {
      migratePanelPreferences(sessionProjectId, null, sessionId)
    },
    [projectId],
  )

  const focusReturnRef = useRef<FocusReturn>({ element: null, actionId: null })
  const focusRestorePendingRef = useRef(false)
  const recordFocusReturn = useCallback((actionId: AgentActionId | null) => {
    const activeElement = document.activeElement
    focusReturnRef.current = {
      element:
        activeElement instanceof HTMLElement && activeElement !== document.body
          ? activeElement
          : null,
      actionId,
    }
  }, [])
  const restoreFocusReturn = useCallback(() => {
    const { element, actionId } = focusReturnRef.current
    if (element?.isConnected) {
      element.focus()
      return true
    }
    const action = actionId
      ? document.querySelector<HTMLButtonElement>(`[data-action-id="${actionId}"]`)
      : null
    if (!action?.isConnected) return false
    action.focus()
    return true
  }, [])
  const ensurePanelFocusReturn = useCallback(() => {
    if (focusReturnRef.current.element?.isConnected || focusReturnRef.current.actionId) return
    focusReturnRef.current = {
      element: null,
      actionId: ACTION_BY_TAB[preferences.activeTab] ?? null,
    }
  }, [preferences.activeTab])
  const close = useCallback(() => {
    ensurePanelFocusReturn()
    focusRestorePendingRef.current = true
    update({ open: false })
  }, [ensurePanelFocusReturn, update])

  const transientWidthRef = useRef(preferences.width)
  const resizingRef = useRef(false)
  const resizeFrameRef = useRef<number | null>(null)
  useEffect(() => {
    if (!resizingRef.current) transientWidthRef.current = preferences.width
  }, [preferences.width])
  const resize = useCallback(
    (delta: number) => {
      resizingRef.current = true
      const next = clampRightSidebarWidth(transientWidthRef.current + delta)
      transientWidthRef.current = next
      if (resizeFrameRef.current !== null) return
      resizeFrameRef.current = window.requestAnimationFrame(() => {
        resizeFrameRef.current = null
        const rail = railRef.current
        if (rail) {
          rail.style.width = `${transientWidthRef.current}px`
          rail.dataset.width = String(transientWidthRef.current)
        }
      })
    },
    [railRef],
  )
  const resizeEnd = useCallback(() => {
    if (resizeFrameRef.current !== null) {
      window.cancelAnimationFrame(resizeFrameRef.current)
      resizeFrameRef.current = null
    }
    resizingRef.current = false
    update({ width: transientWidthRef.current })
  }, [update])

  useEffect(() => {
    if (preferences.open || !focusRestorePendingRef.current) return
    focusRestorePendingRef.current = false
    restoreFocusReturn()
  }, [preferences.open, restoreFocusReturn])

  return {
    panelSessionId,
    setPanelSessionId,
    handoffDraftToSession,
    mobileOpen,
    setMobileOpen,
    preferences,
    update,
    close,
    recordFocusReturn,
    restoreFocusReturn,
    ensurePanelFocusReturn,
    resize,
    resizeEnd,
    isMobile,
  }
}
