"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
} from "react"
import { useTranslations } from "next-intl"
import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent/agent-workbench"
import {
  AgentActionGroup,
  type AgentActionCommandPort,
  type AgentActionId,
  type AgentActionModel,
} from "@/components/bioinfoflow/agent-action-group"
import { LiveDeck, type LiveDeckTab } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"
import type { ConversationSummary } from "@/lib/agent/conversation-model/types"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { FileCode2, Globe, Network, Package } from "@/lib/icons"

const RIGHT_SIDEBAR_MIN = 300
const RIGHT_SIDEBAR_MAX = 600
const RIGHT_SIDEBAR_DEFAULT = 400
const LIVE_DECK_TABS: readonly LiveDeckTab[] = [
  "workspace",
  "browser",
  "artifacts",
  "dag",
]

const liveDeckStorageKey = (projectId: string, key: "open" | "tab") =>
  `agent-live-deck:${projectId}:${key}`

function isLiveDeckTab(value: string | null): value is LiveDeckTab {
  return value !== null && LIVE_DECK_TABS.includes(value as LiveDeckTab)
}

const LIVE_DECK_TAB_BY_ACTION: Record<AgentActionId, LiveDeckTab> = {
  browser: "browser",
  files: "workspace",
  artifacts: "artifacts",
  dag: "dag",
}
const ACTION_BY_LIVE_DECK_TAB: Partial<Record<LiveDeckTab, AgentActionId>> = {
  browser: "browser",
  workspace: "files",
  artifacts: "artifacts",
  dag: "dag",
}
type AgentPanelPreferences = {
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

function writePanelPreferences(
  key: string | null,
  updates: Partial<AgentPanelPreferences>,
): void {
  if (!key || typeof window === "undefined") return
  const current = parsePanelPreferences(readPanelPreferences(key))
  window.localStorage.setItem(key, JSON.stringify({ ...current, ...updates }))
  panelPreferenceListeners.get(key)?.forEach((listener) => listener())
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
    return {
      activeTab,
      open: typeof parsed.open === "boolean" ? parsed.open : DEFAULT_PANEL_PREFERENCES.open,
      width:
        typeof parsed.width === "number"
          ? clampRightSidebarWidth(parsed.width)
          : DEFAULT_PANEL_PREFERENCES.width,
    }
  } catch {
    return DEFAULT_PANEL_PREFERENCES
  }
}

function panelPreferenceKey(
  projectId: string | null,
  routeSessionId: string | null,
): string | null {
  return projectId
    ? `agent-panel:${projectId}:${routeSessionId ?? "draft"}`
    : null
}

export default function AgentPage() {
  return <AgentPageContent routeSessionId={null} />
}

export function AgentPageContent({
  routeSessionId,
}: {
  routeSessionId: string | null
}) {
  const t = useTranslations("agentWorkbench")
  const isMobile = useIsMobile()
  const { setNavbarActions } = useWorkspaceShell()
  const chatRef = useRef<AgentWorkbenchHandle>(null)
  const {
    selectedProjectId,
    conversationProjectId,
    setSelectedProjectId,
    setConversationProjectId,
    activeConversationId,
    setActiveConversationId,
    setActiveConversationTitle,
  } = useProjectContext()
  const [panelSessionId, setPanelSessionId] = useState(
    () => routeSessionId ?? "draft",
  )
  const panelKey = panelPreferenceKey(selectedProjectId, panelSessionId)
  const panelSnapshot = useSyncExternalStore(
    (listener) => subscribeToPanelPreferences(panelKey, listener),
    () => readPanelPreferences(panelKey),
    () => null,
  )
  const panelPreferences = useMemo(
    () => parsePanelPreferences(panelSnapshot),
    [panelSnapshot],
  )
  const liveDeckTab = panelPreferences.activeTab
  const rightSidebarWidth = panelPreferences.width
  const rightSidebarCollapsed = !panelPreferences.open
  const mobileLiveDeckOpen = panelPreferences.open
  const updatePanelPreferences = useCallback(
    (updates: Partial<AgentPanelPreferences>) => {
      writePanelPreferences(panelKey, updates)
    },
    [panelKey],
  )
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
  const [focusedArtifactId, setFocusedArtifactId] = useState<string | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)
  const focusReturnRef = useRef<{
    element: HTMLElement | null
    actionId: AgentActionId | null
  }>({ element: null, actionId: null })
  const focusRestorePendingRef = useRef(false)

  useEffect(() => {
    setActiveConversationId(routeSessionId ?? "")
  }, [routeSessionId, setActiveConversationId])

  useEvents({
    projectId: selectedProjectId,
    onRunDag: (envelope) => {
      if (!selectedRun) return
      if (envelope.data.run_id !== selectedRun.run_id) return
      setDag(envelope.data.dag)
      if (envelope.data.dag) updatePanelPreferences({ activeTab: "dag" })
    },
  })

  const handleRightResize = useCallback((delta: number) => {
    updatePanelPreferences({
      width: clampRightSidebarWidth(rightSidebarWidth + delta),
    })
  }, [rightSidebarWidth, updatePanelPreferences])

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
    if (!actionId) return false
    const action = document.querySelector<HTMLButtonElement>(
      `[data-action-id="${actionId}"]`,
    )
    if (!action?.isConnected) return false
    action.focus()
    return true
  }, [])

  const ensurePanelFocusReturn = useCallback(() => {
    const { element, actionId } = focusReturnRef.current
    if (element?.isConnected || actionId) return
    focusReturnRef.current = {
      element: null,
      actionId: ACTION_BY_LIVE_DECK_TAB[liveDeckTab] ?? null,
    }
  }, [liveDeckTab])

  const toggleRightSidebar = useCallback(() => {
    const nextCollapsed = !rightSidebarCollapsed
    ensurePanelFocusReturn()
    if (nextCollapsed) focusRestorePendingRef.current = true
    updatePanelPreferences({ open: !nextCollapsed })
  }, [ensurePanelFocusReturn, rightSidebarCollapsed, updatePanelPreferences])

  const toggleMobileLiveDeck = useCallback(() => {
    const nextOpen = !mobileLiveDeckOpen
    ensurePanelFocusReturn()
    updatePanelPreferences({ open: nextOpen })
  }, [ensurePanelFocusReturn, mobileLiveDeckOpen, updatePanelPreferences])

  const toggleAction = useCallback(
    (actionId: AgentActionId) => {
      recordFocusReturn(actionId)
      const nextTab = LIVE_DECK_TAB_BY_ACTION[actionId]
      const isActive =
        liveDeckTab === nextTab &&
        (isMobile ? mobileLiveDeckOpen : !rightSidebarCollapsed)

      if (isActive) {
        updatePanelPreferences({ open: false })
        return
      }

      updatePanelPreferences({ activeTab: nextTab, open: true })
    },
    [
      isMobile,
      liveDeckTab,
      mobileLiveDeckOpen,
      recordFocusReturn,
      rightSidebarCollapsed,
      updatePanelPreferences,
    ],
  )

  const actionCommandPort = useMemo<AgentActionCommandPort>(
    () => ({ toggle: toggleAction }),
    [toggleAction],
  )

  useEffect(() => {
    if (!rightSidebarCollapsed || !focusRestorePendingRef.current) return
    focusRestorePendingRef.current = false
    restoreFocusReturn()
  }, [restoreFocusReturn, rightSidebarCollapsed])
  const actionModels = useMemo<AgentActionModel[]>(() => {
    const isLiveDeckOpen = isMobile
      ? mobileLiveDeckOpen
      : !rightSidebarCollapsed
    return [
      {
        id: "browser",
        label: t("workspacePanel.actions.browser"),
        openLabel: t("workspacePanel.actions.openBrowser"),
        closeLabel: t("workspacePanel.actions.closeBrowser"),
        icon: Globe,
        active: isLiveDeckOpen && liveDeckTab === "browser",
        pressed: isLiveDeckOpen && liveDeckTab === "browser",
      },
      {
        id: "files",
        label: t("workspacePanel.actions.files"),
        openLabel: t("workspacePanel.actions.openFiles"),
        closeLabel: t("workspacePanel.actions.closeFiles"),
        icon: FileCode2,
        active: isLiveDeckOpen && liveDeckTab === "workspace",
        pressed: isLiveDeckOpen && liveDeckTab === "workspace",
      },
      {
        id: "artifacts",
        label: t("workspacePanel.actions.artifacts"),
        openLabel: t("workspacePanel.actions.openArtifacts"),
        closeLabel: t("workspacePanel.actions.closeArtifacts"),
        icon: Package,
        active: isLiveDeckOpen && liveDeckTab === "artifacts",
        pressed: isLiveDeckOpen && liveDeckTab === "artifacts",
      },
      {
        id: "dag",
        label: t("workspacePanel.actions.dag"),
        openLabel: t("workspacePanel.actions.openDag"),
        closeLabel: t("workspacePanel.actions.closeDag"),
        icon: Network,
        active: isLiveDeckOpen && liveDeckTab === "dag",
        pressed: isLiveDeckOpen && liveDeckTab === "dag",
      },
    ]
  }, [
    isMobile,
    liveDeckTab,
    mobileLiveDeckOpen,
    rightSidebarCollapsed,
    t,
  ])

  useEffect(() => {
    if (!selectedProjectId) {
      setNavbarActions(null)
      return () => setNavbarActions(null)
    }

    setNavbarActions(
      <AgentActionGroup
        actions={actionModels}
        commandPort={actionCommandPort}
      />,
    )

    return () => setNavbarActions(null)
  }, [
    actionCommandPort,
    actionModels,
    selectedProjectId,
    setNavbarActions,
  ])

  const handleRunSelect = useCallback((run: Run | null) => {
    setSelectedRun(run)
    setFocusedRunId(run?.run_id ?? null)
    setDag(null)
  }, [])

  const openReferencedRun = useCallback(
    (runId: string) => {
      recordFocusReturn(null)
      setSelectedRun(null)
      setFocusedRunId(runId)
      setDag(null)
      updatePanelPreferences({ activeTab: "dag", open: true })
    },
    [recordFocusReturn, updatePanelPreferences],
  )

  const openReferencedArtifact = useCallback(
    (artifactId: string) => {
      recordFocusReturn(null)
      setFocusedArtifactId(artifactId)
      updatePanelPreferences({ activeTab: "artifacts", open: true })
    },
    [recordFocusReturn, updatePanelPreferences],
  )

  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleSessionResolved = useCallback(
    (session: ConversationSummary) => {
      const projectId = session.projectId ?? ""
      setActiveConversationId(session.id)
      setPanelSessionId(session.id)
      setActiveConversationTitle(session.title ?? "")
      setConversationProjectId(projectId)
      setSelectedProjectId(projectId)
    },
    [
      setActiveConversationId,
      setActiveConversationTitle,
      setConversationProjectId,
      setSelectedProjectId,
    ],
  )
  const handleActiveSessionIdChange = useCallback(
    (sessionId: string) => {
      setActiveConversationId(sessionId)
      setPanelSessionId(sessionId || "draft")
    },
    [setActiveConversationId],
  )

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey

      if (mod && event.shiftKey && event.key.toLowerCase() === "b") {
        event.preventDefault()
        if (isMobile) toggleMobileLiveDeck()
        else toggleRightSidebar()
        return
      }

      if (mod && event.key.toLowerCase() === "k") {
        event.preventDefault()
        chatRef.current?.focusInput()
        return
      }

      if (mod && event.key === ".") {
        event.preventDefault()
        chatRef.current?.stop()
        return
      }

      if (mod && event.shiftKey && event.key.toLowerCase() === "n") {
        event.preventDefault()
        chatRef.current?.newConversation()
        return
      }

      if (event.key === "?" && !(event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement)) {
        event.preventDefault()
        setShowShortcuts((prev) => !prev)
        return
      }

      if (event.key === "Escape") {
        if (showShortcuts) {
          setShowShortcuts(false)
          return
        }
        if (isMobile && mobileLiveDeckOpen) {
          updatePanelPreferences({ open: false })
          return
        }
        if (!isMobile && !rightSidebarCollapsed) {
          ensurePanelFocusReturn()
          focusRestorePendingRef.current = true
          updatePanelPreferences({ open: false })
        }
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [
    isMobile,
    liveDeckTab,
    mobileLiveDeckOpen,
    ensurePanelFocusReturn,
    rightSidebarCollapsed,
    restoreFocusReturn,
    showShortcuts,
    toggleMobileLiveDeck,
    toggleRightSidebar,
    updatePanelPreferences,
  ])

  return (
    <div
      className="flex h-full min-h-0 min-w-0 overflow-hidden bg-background"
      data-testid="agent-page-shell"
    >
      <AgentWorkbench
        key={routeSessionId ?? "draft"}
        ref={chatRef}
        projectId={conversationProjectId || selectedProjectId || null}
        sessionId={routeSessionId}
        onActiveSessionIdChange={handleActiveSessionIdChange}
        onSessionResolved={handleSessionResolved}
        onOpenRun={openReferencedRun}
        onOpenArtifact={openReferencedArtifact}
        className="min-w-0 flex-1"
      />
      {showShortcuts && (
        <KeyboardShortcutsOverlay
          open={showShortcuts}
          onOpenChange={setShowShortcuts}
        />
      )}

      {isMobile && selectedProjectId ? (
        <Sheet
          open={mobileLiveDeckOpen}
          onOpenChange={(open) => updatePanelPreferences({ open })}
        >
          <SheetContent
            side="right"
            closeLabel={t("workspacePanel.close")}
            onCloseAutoFocus={(event) => {
              if (restoreFocusReturn()) event.preventDefault()
            }}
            className="w-full max-w-none gap-0 overflow-hidden overscroll-contain p-0 pt-[env(safe-area-inset-top)] pb-[env(safe-area-inset-bottom)] sm:max-w-[32rem]"
          >
            <SheetHeader className="sr-only">
              <SheetTitle>{t("workspacePanel.title")}</SheetTitle>
              <SheetDescription>
                {t("workspacePanel.description")}
              </SheetDescription>
            </SheetHeader>
            <LiveDeck
              activeTab={liveDeckTab}
              onTabChange={(activeTab) => updatePanelPreferences({ activeTab })}
              onCollapse={() => updatePanelPreferences({ open: false })}
              projectId={selectedProjectId}
              sessionId={activeConversationId || routeSessionId}
              selectedArtifactId={focusedArtifactId}
              onSelectedArtifactIdChange={setFocusedArtifactId}
              runId={selectedRun?.run_id ?? focusedRunId}
              dag={dag}
              onRunSelect={handleRunSelect}
            />
          </SheetContent>
        </Sheet>
      ) : null}

      {!isMobile && selectedProjectId && !rightSidebarCollapsed ? (
        <div
          data-testid="agent-live-deck-rail"
          data-width={rightSidebarWidth}
          className="relative flex-shrink-0 animate-in slide-in-from-right-2 fade-in duration-200 motion-reduce:animate-none"
          style={{ width: rightSidebarWidth }}
        >
          <ResizeHandle
            side="right"
            onResize={handleRightResize}
            valueNow={rightSidebarWidth}
            valueMin={RIGHT_SIDEBAR_MIN}
            valueMax={RIGHT_SIDEBAR_MAX}
          />
          <LiveDeck
            activeTab={liveDeckTab}
            onTabChange={(activeTab) => updatePanelPreferences({ activeTab })}
            projectId={selectedProjectId}
            sessionId={activeConversationId || routeSessionId}
            selectedArtifactId={focusedArtifactId}
            onSelectedArtifactIdChange={setFocusedArtifactId}
            runId={selectedRun?.run_id ?? focusedRunId}
            dag={dag}
            onRunSelect={handleRunSelect}
          />
        </div>
      ) : null}
    </div>
  )
}

function clampRightSidebarWidth(value: number) {
  if (!Number.isFinite(value)) return RIGHT_SIDEBAR_DEFAULT
  return Math.min(RIGHT_SIDEBAR_MAX, Math.max(RIGHT_SIDEBAR_MIN, value))
}
