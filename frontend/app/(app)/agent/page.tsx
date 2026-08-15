"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useTranslations } from "next-intl"
import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent/agent-workbench"
import { LiveDeck } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"
import type { SessionView } from "@/lib/agent/contracts"
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
  const chatRef = useRef<AgentWorkbenchHandle>(null)
  const {
    selectedProjectId,
    conversationProjectId,
    setSelectedProjectId,
    setConversationProjectId,
    setActiveConversationId,
    setActiveConversationTitle,
  } = useProjectContext()
  const [liveDeckTab, setLiveDeckTab] = useState<"workspace" | "dag" | "monitor">("workspace")
  const [rightSidebarWidth, setRightSidebarWidth] = useState(RIGHT_SIDEBAR_DEFAULT)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(true)
  const [mobileLiveDeckOpen, setMobileLiveDeckOpen] = useState(false)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [focusedRunId, setFocusedRunId] = useState<string | null>(null)
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

  const [showShortcuts, setShowShortcuts] = useState(false)

  const handleSessionResolved = useCallback(
    (session: SessionView) => {
      const projectId = session.project_id ?? ""
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
        className="min-w-0 flex-1"
        headerActions={
          selectedProjectId ? (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="min-h-11 gap-2 px-3 lg:min-h-9"
              aria-label={t(
                !isMobile && !rightSidebarCollapsed
                  ? "workspacePanel.close"
                  : "workspacePanel.open",
              )}
              onClick={() => {
                if (isMobile) setMobileLiveDeckOpen(true)
                else toggleRightSidebar()
              }}
            >
              <PanelRightClose
                aria-hidden="true"
                className={rightSidebarCollapsed || isMobile ? "rotate-180" : undefined}
              />
              <span>{t("workspacePanel.action")}</span>
            </Button>
          ) : null
        }
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
            onCollapse={toggleRightSidebar}
            projectId={selectedProjectId}
            runId={selectedRun?.run_id ?? focusedRunId}
            dag={dag}
            onRunSelect={handleRunSelect}
          />
        </div>
      ) : null}
    </div>
  )
}
