"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"
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
  const [liveDeckTab, setLiveDeckTab] = useState<LiveDeckTab>("workspace")
  const [rightSidebarWidth, setRightSidebarWidth] = useState(RIGHT_SIDEBAR_DEFAULT)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(true)
  const [mobileLiveDeckOpen, setMobileLiveDeckOpen] = useState(false)
  const [liveDeckStorageProjectId, setLiveDeckStorageProjectId] = useState<
    string | null
  >(null)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
  const [focusedArtifactId, setFocusedArtifactId] = useState<string | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)
  const lastActionIdRef = useRef<AgentActionId | null>(null)

  useEffect(() => {
    setActiveConversationId(routeSessionId ?? "")
  }, [routeSessionId, setActiveConversationId])

  useEffect(() => {
    const savedWidth = localStorage.getItem("right-sidebar-width")
    const savedCollapsed = localStorage.getItem("right-sidebar-collapsed")
    /* eslint-disable react-hooks/set-state-in-effect */
    if (savedWidth) setRightSidebarWidth(clampRightSidebarWidth(Number(savedWidth)))
    if (savedCollapsed) setRightSidebarCollapsed(savedCollapsed === "true")
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [])

  useEffect(() => {
    if (!selectedProjectId) {
      /* eslint-disable react-hooks/set-state-in-effect */
      setLiveDeckStorageProjectId(null)
      /* eslint-enable react-hooks/set-state-in-effect */
      return
    }

    const storedTab = localStorage.getItem(
      liveDeckStorageKey(selectedProjectId, "tab"),
    )
    const storedOpen =
      localStorage.getItem(liveDeckStorageKey(selectedProjectId, "open")) ===
      "true"

    if (isLiveDeckTab(storedTab)) setLiveDeckTab(storedTab)
    setMobileLiveDeckOpen(isMobile && storedOpen)
    setLiveDeckStorageProjectId(selectedProjectId)
  }, [isMobile, selectedProjectId])

  useEffect(() => {
    if (
      !selectedProjectId ||
      liveDeckStorageProjectId !== selectedProjectId
    ) {
      return
    }
    localStorage.setItem(
      liveDeckStorageKey(selectedProjectId, "tab"),
      liveDeckTab,
    )
    localStorage.setItem(
      liveDeckStorageKey(selectedProjectId, "open"),
      String(isMobile && mobileLiveDeckOpen),
    )
  }, [
    isMobile,
    liveDeckStorageProjectId,
    liveDeckTab,
    mobileLiveDeckOpen,
    selectedProjectId,
  ])

  // Persist state
  useEffect(() => {
    localStorage.setItem("right-sidebar-width", String(rightSidebarWidth))
  }, [rightSidebarWidth])

  useEffect(() => {
    localStorage.setItem("right-sidebar-collapsed", String(rightSidebarCollapsed))
  }, [rightSidebarCollapsed])

  useEvents({
    projectId: selectedProjectId,
    onRunDag: (envelope) => {
      if (!selectedRun) return
      if (envelope.data.run_id !== selectedRun.run_id) return
      setDag(envelope.data.dag)
      if (envelope.data.dag) setLiveDeckTab("dag")
    },
  })

  const handleRightResize = useCallback((delta: number) => {
    setRightSidebarWidth((prev) => {
      return clampRightSidebarWidth(prev + delta)
    })
  }, [])

  const toggleRightSidebar = useCallback(() => {
    setRightSidebarCollapsed((prev) => !prev)
  }, [])

  const toggleAction = useCallback(
    (actionId: AgentActionId) => {
      lastActionIdRef.current = actionId
      const nextTab = LIVE_DECK_TAB_BY_ACTION[actionId]
      const isActive =
        liveDeckTab === nextTab &&
        (isMobile ? mobileLiveDeckOpen : !rightSidebarCollapsed)

      if (isActive) {
        if (isMobile) setMobileLiveDeckOpen(false)
        else setRightSidebarCollapsed(true)
        return
      }

      setLiveDeckTab(nextTab)
      if (isMobile) setMobileLiveDeckOpen(true)
      else setRightSidebarCollapsed(false)
    },
    [
      isMobile,
      liveDeckTab,
      mobileLiveDeckOpen,
      rightSidebarCollapsed,
    ],
  )

  const restoreActionFocus = useCallback(() => {
    const actionId = lastActionIdRef.current
    if (!actionId) return
    document
      .querySelector<HTMLButtonElement>(`[data-action-id="${actionId}"]`)
      ?.focus()
  }, [])

  const actionCommandPort = useMemo<AgentActionCommandPort>(
    () => ({ toggle: toggleAction }),
    [toggleAction],
  )
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
      setSelectedRun(null)
      setFocusedRunId(runId)
      setDag(null)
      setLiveDeckTab("dag")
      if (isMobile) setMobileLiveDeckOpen(true)
      else setRightSidebarCollapsed(false)
    },
    [isMobile],
  )

  const openReferencedArtifact = useCallback(
    (artifactId: string) => {
      setFocusedArtifactId(artifactId)
      setLiveDeckTab("artifacts")
      if (isMobile) setMobileLiveDeckOpen(true)
      else setRightSidebarCollapsed(false)
    },
    [isMobile],
  )

  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleSessionResolved = useCallback(
    (session: ConversationSummary) => {
      const projectId = session.projectId ?? ""
      setActiveConversationId(session.id)
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

  // Keyboard shortcuts
  useEffect(() => {
    const handler = (event: KeyboardEvent) => {
      const mod = event.metaKey || event.ctrlKey

      if (mod && event.shiftKey && event.key.toLowerCase() === "b") {
        event.preventDefault()
        toggleRightSidebar()
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
          setMobileLiveDeckOpen(false)
          queueMicrotask(restoreActionFocus)
          return
        }
        if (!isMobile && !rightSidebarCollapsed) {
          setRightSidebarCollapsed(true)
        }
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [
    isMobile,
    mobileLiveDeckOpen,
    rightSidebarCollapsed,
    restoreActionFocus,
    showShortcuts,
    toggleRightSidebar,
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
        onActiveSessionIdChange={setActiveConversationId}
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
        <Sheet open={mobileLiveDeckOpen} onOpenChange={setMobileLiveDeckOpen}>
          <SheetContent
            side="right"
            closeLabel={t("workspacePanel.close")}
            onCloseAutoFocus={(event) => {
              event.preventDefault()
              restoreActionFocus()
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
              onTabChange={setLiveDeckTab}
              onCollapse={() => setMobileLiveDeckOpen(false)}
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
            onTabChange={setLiveDeckTab}
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
