"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent/agent-workbench"
import { LiveDeck, type LiveDeckTab } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"
import type { ConversationSummary } from "@/lib/agent/conversation-model/types"
import { Button } from "@/components/ui/button"
import {
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet"
import { PanelRightClose } from "@/lib/icons"

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

  useEffect(() => {
    setActiveConversationId(routeSessionId ?? "")
  }, [routeSessionId, setActiveConversationId])

  useEffect(() => {
    const savedWidth = localStorage.getItem("right-sidebar-width")
    const savedCollapsed = localStorage.getItem("right-sidebar-collapsed")
    /* eslint-disable react-hooks/set-state-in-effect */
    if (savedWidth) setRightSidebarWidth(Number(savedWidth))
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
      const next = prev + delta
      return Math.min(RIGHT_SIDEBAR_MAX, Math.max(RIGHT_SIDEBAR_MIN, next))
    })
  }, [])

  const toggleRightSidebar = useCallback(() => {
    setRightSidebarCollapsed((prev) => !prev)
  }, [])
  const workspaceActionLabel = t(
    !isMobile && !rightSidebarCollapsed
      ? "workspacePanel.close"
      : "workspacePanel.open",
  )

  useEffect(() => {
    if (!selectedProjectId) {
      setNavbarActions(null)
      return () => setNavbarActions(null)
    }

    setNavbarActions(
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="h-8 w-8 rounded-lg border border-transparent bg-transparent text-foreground/78 transition-colors hover:bg-accent/70 hover:text-foreground"
        aria-label={workspaceActionLabel}
        onClick={() => {
          if (isMobile) setMobileLiveDeckOpen(true)
          else toggleRightSidebar()
        }}
      >
        <PanelRightClose
          aria-hidden="true"
          className={rightSidebarCollapsed || isMobile ? "rotate-180" : undefined}
        />
      </Button>,
    )

    return () => setNavbarActions(null)
  }, [
    isMobile,
    rightSidebarCollapsed,
    selectedProjectId,
    setNavbarActions,
    toggleRightSidebar,
    workspaceActionLabel,
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

      if (event.key === "Escape" && showShortcuts) {
        setShowShortcuts(false)
      }
    }
    window.addEventListener("keydown", handler)
    return () => window.removeEventListener("keydown", handler)
  }, [toggleRightSidebar, showShortcuts])

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
          className="relative flex-shrink-0 animate-in slide-in-from-right-2 fade-in duration-200 motion-reduce:animate-none"
          style={{ width: rightSidebarWidth }}
        >
          <ResizeHandle side="right" onResize={handleRightResize} />
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
