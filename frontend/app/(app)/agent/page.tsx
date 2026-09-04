"use client"

import {
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react"
import { useTranslations } from "next-intl"
import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent/agent-workbench"
import {
  type AgentActionId,
} from "@/components/bioinfoflow/agent-action-group"
import {
  AgentWorkspaceActionGroup,
  type AgentWorkspaceTab,
} from "@/components/bioinfoflow/agent/agent-workspace-action-group"
import { LiveDeck, type LiveDeckTab } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useEvents } from "@/hooks/use-events"
import {
  RIGHT_SIDEBAR_MAX,
  RIGHT_SIDEBAR_MIN,
  useAgentPanelController,
} from "@/hooks/use-agent-panel-controller"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile, useMediaQuery } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"
import type { ConversationSummary } from "@/lib/agent/conversation-model/types"
import {
  listConversationRouteSummaries,
  type ConversationRouteSummary,
} from "@/lib/agent/conversation-model/session-directory"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
const LIVE_DECK_TAB_BY_ACTION: Record<AgentActionId, LiveDeckTab> = {
  browser: "browser",
  files: "workspace",
  artifacts: "artifacts",
  dag: "dag",
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
  const tAccessibility = useTranslations("accessibility")
  const isMobile = useIsMobile()
  const viewportUsesSheet = useMediaQuery("(max-width: 1279px)")
  const workspaceUsesSheet = isMobile || viewportUsesSheet
  const {
    setNavbarActions,
    projectConversations,
  } = useWorkspaceShell()
  const chatRef = useRef<AgentWorkbenchHandle>(null)
  const {
    selectedProjectId,
    conversationProjectId,
    setSelectedProjectId,
    setConversationProjectId,
    setActiveConversationId,
    setActiveConversationTitle,
  } = useProjectContext()
  const railRef = useRef<HTMLDivElement>(null)
  const [routeResolution, setRouteResolution] = useState<{
    sessionId: string | null
    status: "ready" | "loading" | "unavailable" | "error"
    session: ConversationRouteSummary | null
  }>({
    sessionId: routeSessionId,
    status: routeSessionId && projectConversations !== undefined ? "loading" : "ready",
    session: null,
  })
  const resolvedRouteSession =
    routeResolution.sessionId === routeSessionId
      ? routeResolution.session
      : null
  const routeResolutionState =
    !routeSessionId ||
    projectConversations === undefined
      ? "ready"
      : routeResolution.sessionId !== routeSessionId
        ? "loading"
      : routeResolution.status
  const effectiveProjectId = routeSessionId
    ? projectConversations === undefined
      ? conversationProjectId || selectedProjectId
      : resolvedRouteSession?.projectId ?? null
    : selectedProjectId
  const {
    preferences: panelPreferences,
    update: updatePanelPreferences,
    close: closeLiveDeck,
    recordFocusReturn,
    restoreFocusReturn,
    ensurePanelFocusReturn,
    resize: handleRightResize,
    resizeEnd: handleRightResizeEnd,
    setPanelSessionId,
    handoffDraftToSession,
    mobileOpen,
    setMobileOpen,
  } = useAgentPanelController({
    projectId: effectiveProjectId,
    routeSessionId,
    isMobile,
    railRef,
  })
  const liveDeckTab = panelPreferences.activeTab
  const rightSidebarWidth = panelPreferences.width
  const rightSidebarCollapsed = !panelPreferences.open
  const mobileLiveDeckOpen = mobileOpen
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
  const [focusedArtifactId, setFocusedArtifactId] = useState<string | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)
  const sessionScope = routeSessionId || "draft"
  const projectScope = effectiveProjectId || "none"
  const stateIdentity = `${projectScope}:${sessionScope}`
  const [activeStateIdentity, setActiveStateIdentity] = useState(stateIdentity)
  const hasCurrentState = activeStateIdentity === stateIdentity
  const visibleSelectedRun = hasCurrentState ? selectedRun : null
  const visibleFocusedRunId = hasCurrentState ? focusedRunId : null
  const visibleFocusedArtifactId = hasCurrentState ? focusedArtifactId : null
  const visibleDag = hasCurrentState ? dag : null

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect */
    setSelectedRun(null)
    setFocusedRunId(null)
    setFocusedArtifactId(null)
    setDag(null)
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [routeSessionId])

  useEffect(() => {
    if (!routeSessionId || projectConversations === undefined) return
    let cancelled = false
    void listConversationRouteSummaries({ includeArchived: true })
      .then((sessions) => {
        if (cancelled) return
        const session = sessions.find((item) => item.id === routeSessionId)
        setRouteResolution({
          sessionId: routeSessionId,
          status: session ? "ready" : "unavailable",
          session: session ?? null,
        })
      })
      .catch(() => {
        if (cancelled) return
        setRouteResolution({
          sessionId: routeSessionId,
          status: "error",
          session: null,
        })
      })
    return () => {
      cancelled = true
    }
  }, [projectConversations, routeSessionId])

  useEffect(() => {
    setActiveConversationId(routeSessionId ?? "")
  }, [routeSessionId, setActiveConversationId])

  useEvents({
    projectId: effectiveProjectId,
    onRunDag: (envelope) => {
      if (!visibleSelectedRun) return
      if (envelope.data.run_id !== visibleSelectedRun.run_id) return
      setDag(envelope.data.dag)
      if (envelope.data.dag) updatePanelPreferences({ activeTab: "dag" })
    },
  })

  const toggleRightSidebar = useCallback(() => {
    const nextCollapsed = !rightSidebarCollapsed
    if (nextCollapsed) {
      closeLiveDeck()
      return
    }
    ensurePanelFocusReturn()
    updatePanelPreferences({ open: !nextCollapsed })
  }, [
    closeLiveDeck,
    ensurePanelFocusReturn,
    rightSidebarCollapsed,
    updatePanelPreferences,
  ])

  const closeMobileLiveDeck = useCallback(() => {
    ensurePanelFocusReturn()
    setMobileOpen(false)
  }, [ensurePanelFocusReturn, setMobileOpen])

  const toggleMobileLiveDeck = useCallback(() => {
    const nextOpen = !mobileLiveDeckOpen
    if (!nextOpen) {
      closeMobileLiveDeck()
      return
    }
    ensurePanelFocusReturn()
    setMobileOpen(true)
  }, [
    closeMobileLiveDeck,
    ensurePanelFocusReturn,
    mobileLiveDeckOpen,
    setMobileOpen,
  ])

  const toggleAction = useCallback(
    (actionId: AgentActionId) => {
      recordFocusReturn(actionId)
      const nextTab = LIVE_DECK_TAB_BY_ACTION[actionId]
      const isActive =
        liveDeckTab === nextTab &&
        (workspaceUsesSheet ? mobileLiveDeckOpen : !rightSidebarCollapsed)

      if (isActive) {
        if (workspaceUsesSheet) {
          closeMobileLiveDeck()
        } else {
          closeLiveDeck()
        }
        return
      }

      if (workspaceUsesSheet) {
        setMobileOpen(true)
        updatePanelPreferences({ activeTab: nextTab })
      } else {
        updatePanelPreferences({ activeTab: nextTab, open: true })
      }
    },
    [
      liveDeckTab,
      mobileLiveDeckOpen,
      setMobileOpen,
      recordFocusReturn,
      rightSidebarCollapsed,
      updatePanelPreferences,
      closeLiveDeck,
      closeMobileLiveDeck,
      workspaceUsesSheet,
    ],
  )

  const openWorkspaceTab = useCallback(
    (tab: AgentWorkspaceTab) => {
      toggleAction(tab as AgentActionId)
    },
    [toggleAction],
  )
  const toggleWorkspacePanel = useCallback(() => {
    if (workspaceUsesSheet) toggleMobileLiveDeck()
    else toggleRightSidebar()
  }, [toggleMobileLiveDeck, toggleRightSidebar, workspaceUsesSheet])
  const closeWorkspacePanel = useCallback(() => {
    if (workspaceUsesSheet) closeMobileLiveDeck()
    else closeLiveDeck()
  }, [closeLiveDeck, closeMobileLiveDeck, workspaceUsesSheet])
  const workspacePanelOpen = workspaceUsesSheet
    ? mobileLiveDeckOpen
    : !rightSidebarCollapsed

  useEffect(() => {
    if (!effectiveProjectId) {
      setNavbarActions(null)
      return () => setNavbarActions(null)
    }

    setNavbarActions(
      <AgentWorkspaceActionGroup
        activeTab={liveDeckTab === "workspace" ? "files" : liveDeckTab}
        panelOpen={workspacePanelOpen}
        labels={{
          group: t("workspacePanel.action"),
          artifacts: t("workspacePanel.actions.openArtifacts"),
          files: t("workspacePanel.actions.openFiles"),
          dag: t("workspacePanel.actions.openDag"),
          browser: t("workspacePanel.actions.openBrowser"),
          openPanel: t("workspacePanel.open"),
          closePanel: t("workspacePanel.close"),
          closeTab: tAccessibility("hidePanel"),
        }}
        onOpenTab={openWorkspaceTab}
        onTogglePanel={toggleWorkspacePanel}
        onCloseTab={closeWorkspacePanel}
      />,
    )

    return () => setNavbarActions(null)
  }, [
    closeWorkspacePanel,
    effectiveProjectId,
    liveDeckTab,
    openWorkspaceTab,
    setNavbarActions,
    t,
    tAccessibility,
    toggleWorkspacePanel,
    workspacePanelOpen,
  ])

  const handleRunSelect = useCallback((run: Run | null) => {
    setActiveStateIdentity(stateIdentity)
    setSelectedRun(run)
    setFocusedRunId(run?.run_id ?? null)
    setDag(null)
  }, [stateIdentity])

  const openReferencedRun = useCallback(
    (runId: string) => {
      recordFocusReturn(null)
      setActiveStateIdentity(stateIdentity)
      setSelectedRun(null)
      setFocusedRunId(runId)
      setDag(null)
      if (workspaceUsesSheet) {
        setMobileOpen(true)
        updatePanelPreferences({ activeTab: "dag" })
      } else {
        updatePanelPreferences({ activeTab: "dag", open: true })
      }
    },
    [
      recordFocusReturn,
      setMobileOpen,
      stateIdentity,
      updatePanelPreferences,
      workspaceUsesSheet,
    ],
  )

  const openReferencedArtifact = useCallback(
    (artifactId: string) => {
      recordFocusReturn(null)
      setSelectedRun(null)
      setFocusedRunId(null)
      setDag(null)
      setActiveStateIdentity(stateIdentity)
      setFocusedArtifactId(artifactId)
      if (workspaceUsesSheet) {
        setMobileOpen(true)
        updatePanelPreferences({ activeTab: "artifacts" })
      } else {
        updatePanelPreferences({ activeTab: "artifacts", open: true })
      }
    },
    [
      recordFocusReturn,
      setMobileOpen,
      stateIdentity,
      updatePanelPreferences,
      workspaceUsesSheet,
    ],
  )
  const handleSelectedArtifactIdChange = useCallback(
    (artifactId: string | null) => {
      setSelectedRun(null)
      setFocusedRunId(null)
      setDag(null)
      setActiveStateIdentity(stateIdentity)
      setFocusedArtifactId(artifactId)
    },
    [stateIdentity],
  )

  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleBeforeSessionRoute = useCallback(
    (sessionId: string) => {
      if (!routeSessionId) handoffDraftToSession(sessionId)
    },
    [handoffDraftToSession, routeSessionId],
  )

  const handleSessionResolved = useCallback(
    (session: ConversationSummary) => {
      const projectId = session.projectId ?? ""
      if (!routeSessionId) handoffDraftToSession(session.id, projectId)
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
      setPanelSessionId,
      handoffDraftToSession,
      routeSessionId,
    ],
  )
  const handleActiveSessionIdChange = useCallback(
    (sessionId: string) => {
      setActiveConversationId(sessionId)
      setPanelSessionId(sessionId || "draft")
    },
    [setActiveConversationId, setPanelSessionId],
  )

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey

      if (event.defaultPrevented) return

      if (mod && event.shiftKey && event.key.toLowerCase() === "b") {
        event.preventDefault()
        if (workspaceUsesSheet) toggleMobileLiveDeck()
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
        if (workspaceUsesSheet && mobileLiveDeckOpen) {
          closeMobileLiveDeck()
          return
        }
        if (!workspaceUsesSheet && !rightSidebarCollapsed) {
          closeLiveDeck()
        }
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [
    mobileLiveDeckOpen,
    ensurePanelFocusReturn,
    rightSidebarCollapsed,
    restoreFocusReturn,
    showShortcuts,
    toggleMobileLiveDeck,
    toggleRightSidebar,
    setMobileOpen,
    closeLiveDeck,
    closeMobileLiveDeck,
    workspaceUsesSheet,
  ])

  if (routeSessionId && routeResolutionState !== "ready") {
    return (
      <div
        className="flex h-full min-h-0 min-w-0 items-center justify-center bg-background"
        data-testid="agent-route-resolution"
        data-route-state={routeResolutionState}
        role="status"
      >
        {routeResolutionState === "loading"
          ? (
              <>
                <span>{t("routeLoading.title")}</span>
                <span>{t("routeLoading.description")}</span>
              </>
            )
          : t("loadErrorTitle")}
      </div>
    )
  }

  return (
    <div
      className="flex h-full min-h-0 min-w-0 overflow-hidden bg-background"
      data-testid="agent-page-shell"
    >
      <AgentWorkbench
        key={`${effectiveProjectId ?? "none"}:${routeSessionId ?? "draft"}`}
        ref={chatRef}
        projectId={routeSessionId ? effectiveProjectId : conversationProjectId || effectiveProjectId || null}
        sessionId={routeSessionId}
        onBeforeSessionRoute={handleBeforeSessionRoute}
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

      {workspaceUsesSheet && effectiveProjectId ? (
        <Sheet
          open={mobileLiveDeckOpen}
          onOpenChange={(open) => {
            if (open) setMobileOpen(true)
            else closeMobileLiveDeck()
          }}
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
              onCollapse={closeMobileLiveDeck}
          projectId={effectiveProjectId}
              sessionId={routeSessionId}
              selectedArtifactId={visibleFocusedArtifactId}
              onSelectedArtifactIdChange={handleSelectedArtifactIdChange}
              runId={visibleSelectedRun?.run_id ?? visibleFocusedRunId}
              dag={visibleDag}
              onRunSelect={handleRunSelect}
            />
          </SheetContent>
        </Sheet>
      ) : null}

      {!workspaceUsesSheet && effectiveProjectId && !rightSidebarCollapsed ? (
        <div
          ref={railRef}
          data-testid="agent-live-deck-rail"
          data-width={rightSidebarWidth}
          className="relative flex-shrink-0 animate-in slide-in-from-right-2 fade-in duration-200 motion-reduce:animate-none"
          style={{ width: rightSidebarWidth }}
        >
          <ResizeHandle
            side="right"
            onResize={handleRightResize}
            onResizeEnd={handleRightResizeEnd}
            valueNow={rightSidebarWidth}
            valueMin={RIGHT_SIDEBAR_MIN}
            valueMax={RIGHT_SIDEBAR_MAX}
            ariaLabel={tAccessibility("resizePanel")}
          />
          <LiveDeck
            activeTab={liveDeckTab}
            onTabChange={(activeTab) => updatePanelPreferences({ activeTab })}
            onCollapse={closeLiveDeck}
        projectId={effectiveProjectId}
            sessionId={routeSessionId}
            selectedArtifactId={visibleFocusedArtifactId}
            onSelectedArtifactIdChange={handleSelectedArtifactIdChange}
            runId={visibleSelectedRun?.run_id ?? visibleFocusedRunId}
            dag={visibleDag}
            onRunSelect={handleRunSelect}
          />
        </div>
      ) : null}
    </div>
  )
}

