"use client"

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"
import type { LiveDeckTab } from "@/components/bioinfoflow/live-deck"
import type { AgentWorkspaceTab } from "@/lib/agent/drawer-tabs"
import {
  addDrawerTab,
  closeDrawerTab,
  drawerToolTab,
  isDrawerTab,
  type AgentDrawerTab,
} from "@/lib/agent/drawer-tabs"

export const RIGHT_SIDEBAR_MIN = 300
export const RIGHT_SIDEBAR_MAX = 600
const RIGHT_SIDEBAR_DEFAULT = 400
const DRAWER_WIDTH_PREFERENCE_KEY = "agent-panel:drawer-width"

export type AgentPanelPreferences = {
  activeTab: LiveDeckTab
  activeTabId: string | null
  open: boolean
  tabs: AgentDrawerTab[]
  width: number
}

const DEFAULT_PANEL_PREFERENCES: AgentPanelPreferences = {
  activeTab: "workspace",
  activeTabId: null,
  open: false,
  tabs: [],
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
    const activeTab =
        parsed.activeTab === "workspace" ||
        parsed.activeTab === "dag" ||
        parsed.activeTab === "artifacts" ||
        parsed.activeTab === "browser"
          ? parsed.activeTab
          : DEFAULT_PANEL_PREFERENCES.activeTab
    const tabs = Array.isArray(parsed.tabs)
      ? parsed.tabs.filter(isDrawerTab)
      : raw.includes('"activeTab"')
        ? [drawerToolTab(activeTab)]
        : []
    const activeTabId =
      typeof parsed.activeTabId === "string" && tabs.some((tab) => tab.id === parsed.activeTabId)
        ? parsed.activeTabId
        : tabs.find((tab) => tab.kind === activeTab)?.id ?? tabs.at(-1)?.id ?? null
    return {
      activeTab,
      activeTabId,
      open:
        typeof parsed.open === "boolean"
          ? parsed.open
          : DEFAULT_PANEL_PREFERENCES.open,
      tabs,
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
  const next = { ...current, ...updates }
  const sessionState = { ...next }
  delete sessionState.width
  window.localStorage.setItem(key, JSON.stringify(sessionState))
  panelPreferenceListeners.get(key)?.forEach((listener) => listener())
}

function readDrawerWidthPreference(): number | null {
  if (typeof window === "undefined") return null
  const raw = window.localStorage.getItem(DRAWER_WIDTH_PREFERENCE_KEY)
  if (!raw) return null
  const value = Number(raw)
  return Number.isFinite(value) ? clampRightSidebarWidth(value) : null
}

function writeDrawerWidthPreference(width: number) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(DRAWER_WIDTH_PREFERENCE_KEY, String(clampRightSidebarWidth(width)))
  panelPreferenceListeners.get(DRAWER_WIDTH_PREFERENCE_KEY)?.forEach((listener) => listener())
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
  const target = readPanelPreferences(targetKey)
  if (source && !target) {
    const sessionState = parsePanelPreferences(source)
    delete sessionState.width
    window.localStorage.setItem(targetKey, JSON.stringify(sessionState))
    window.localStorage.removeItem(sourceKey)
  }

  const sourceMobileKey = mobilePreferenceKey(sourceKey)
  const targetMobileKey = mobilePreferenceKey(targetKey)
  const sourceMobile = readPanelPreferences(sourceMobileKey)
  const targetMobile = readPanelPreferences(targetMobileKey)
  if (sourceMobile && !targetMobile) {
    window.localStorage.setItem(targetMobileKey!, sourceMobile)
    window.localStorage.removeItem(sourceMobileKey!)
  }

  if (source && !target) {
    panelPreferenceListeners.get(targetKey)?.forEach((listener) => listener())
    panelPreferenceListeners.get(sourceKey)?.forEach((listener) => listener())
  }
  if (sourceMobile && !targetMobile) {
    panelPreferenceListeners.get(targetMobileKey!)?.forEach((listener) => listener())
    panelPreferenceListeners.get(sourceMobileKey!)?.forEach((listener) => listener())
  }
}

const getServerPanelPreferences = () => null

type FocusReturn = {
  element: HTMLElement | null
  actionId: AgentWorkspaceTab | "panel" | null
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
  const storedPreferences = parsePanelPreferences(panelSnapshot)
  const subscribeWidth = useCallback(
    (listener: () => void) => subscribeToPanelPreferences(DRAWER_WIDTH_PREFERENCE_KEY, listener),
    [],
  )
  const widthSnapshot = useSyncExternalStore(
    subscribeWidth,
    () => typeof window === "undefined" ? null : window.localStorage.getItem(DRAWER_WIDTH_PREFERENCE_KEY),
    getServerPanelPreferences,
  )
  const preferences = {
    ...storedPreferences,
    width: (widthSnapshot === null ? null : readDrawerWidthPreference()) ?? storedPreferences.width,
  }
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
    (updates: Partial<AgentPanelPreferences>) => {
      if (typeof updates.width === "number") writeDrawerWidthPreference(updates.width)
      const sessionUpdates = { ...updates }
      delete sessionUpdates.width
      if (Object.keys(sessionUpdates).length > 0) writePanelPreferences(key, sessionUpdates)
    },
    [key],
  )
  const selectTab = useCallback(
    (tab: AgentDrawerTab) => {
      const current = parsePanelPreferences(readPanelPreferences(key))
      const next = addDrawerTab(current.tabs, current.activeTabId, tab)
      update({
        activeTab: liveDeckTabForDrawerTab(tab),
        activeTabId: next.activeTabId,
        tabs: next.tabs,
      })
    },
    [key, update],
  )
  const closeTab = useCallback(
    (tabId: string) => {
      const current = parsePanelPreferences(readPanelPreferences(key))
      const next = closeDrawerTab(current.tabs, current.activeTabId, tabId)
      const active = next.tabs.find((tab) => tab.id === next.activeTabId)
      update({
        activeTab: active ? liveDeckTabForDrawerTab(active) : DEFAULT_PANEL_PREFERENCES.activeTab,
        activeTabId: next.activeTabId,
        tabs: next.tabs,
        open: next.tabs.length > 0 ? current.open : false,
      })
      if (next.tabs.length === 0) setMobileOpen(false)
    },
    [key, setMobileOpen, update],
  )
  const selectExistingTab = useCallback(
    (tabId: string) => {
      const current = parsePanelPreferences(readPanelPreferences(key))
      const tab = current.tabs.find((item) => item.id === tabId)
      if (!tab) return
      update({ activeTab: liveDeckTabForDrawerTab(tab), activeTabId: tab.id })
    },
    [key, update],
  )
  const handoffDraftToSession = useCallback(
    (sessionId: string, sessionProjectId = projectId) => {
      migratePanelPreferences(sessionProjectId, null, sessionId)
    },
    [projectId],
  )

  const focusReturnRef = useRef<FocusReturn>({ element: null, actionId: null })
  const focusRestorePendingRef = useRef(false)
  const recordFocusReturn = useCallback((actionId: AgentWorkspaceTab | "panel" | null) => {
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
      actionId: "panel",
    }
  }, [])
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
    selectTab,
    selectExistingTab,
    closeTab,
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

function liveDeckTabForDrawerTab(tab: AgentDrawerTab): LiveDeckTab {
  if (tab.kind === "file") return "workspace"
  if (tab.kind === "artifact") return "artifacts"
  return tab.kind
}
