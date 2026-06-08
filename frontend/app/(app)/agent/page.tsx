"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { AgentCoreChat, type AgentCoreChatHandle } from "@/components/bioinfoflow/agent-core/agent-core-chat"
import { LiveDeck } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"

const RIGHT_SIDEBAR_MIN = 300
const RIGHT_SIDEBAR_MAX = 600
const RIGHT_SIDEBAR_DEFAULT = 400
const LAST_USED_PROJECT_STORAGE_KEY = "bioinfoflow:last-used-project"

export default function AgentPage() {
  const { selectedProjectId, conversationProjectId, activeConversationId } = useProjectContext()

  return (
    <AgentPageContent
      key={`${selectedProjectId || "no-selected"}:${conversationProjectId || "no-conversation-project"}:${activeConversationId || "draft"}`}
      selectedProjectId={selectedProjectId}
      conversationProjectId={conversationProjectId}
      activeConversationId={activeConversationId}
    />
  )
}

function AgentPageContent({
  selectedProjectId,
  conversationProjectId,
  activeConversationId,
}: {
  selectedProjectId: string
  conversationProjectId: string
  activeConversationId: string
}) {
  const isMobile = useIsMobile()
  const chatRef = useRef<AgentCoreChatHandle>(null)
  const workspaceShell = useOptionalWorkspaceShell()
  const { setActiveConversationId, setActiveProjectId } = useProjectContext()
  const [liveDeckTab, setLiveDeckTab] = useState<"workspace" | "dag" | "monitor">("workspace")
  const [rightSidebarWidth, setRightSidebarWidth] = useState(RIGHT_SIDEBAR_DEFAULT)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(true)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)

  // Load persisted state from localStorage (runs once after hydration)
  useEffect(() => {
    if (selectedProjectId || conversationProjectId) {
      return
    }

    const regularProjects =
      workspaceShell?.projects?.filter((project) => !project.is_default) ?? []
    if (regularProjects.length === 0) {
      return
    }

    const storedProjectId =
      window.localStorage.getItem(LAST_USED_PROJECT_STORAGE_KEY) ?? ""
    const restoredProject =
      regularProjects.find((project) => project.id === storedProjectId) ??
      regularProjects[0]

    if (restoredProject) {
      setActiveProjectId(restoredProject.id)
    }
  }, [
    conversationProjectId,
    selectedProjectId,
    setActiveProjectId,
    workspaceShell?.projects,
  ])

  useEffect(() => {
    const savedWidth = localStorage.getItem("right-sidebar-width")
    /* eslint-disable react-hooks/set-state-in-effect */
    if (savedWidth) setRightSidebarWidth(Number(savedWidth))
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
    setDag(null)
  }, [])

  const [showShortcuts, setShowShortcuts] = useState(false)

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
    <div className="flex h-full bg-background">
      <AgentCoreChat
        ref={chatRef}
        projectId={conversationProjectId}
        activeSessionId={activeConversationId}
        onActiveSessionIdChange={setActiveConversationId}
        workspaceEnabled={Boolean(conversationProjectId)}
        onQuickCreateProject={workspaceShell?.handleQuickCreateProject}
        onOpenCreateProjectDialog={workspaceShell?.openCreateProjectDialog}
        className="flex-1"
      />
      {showShortcuts && (
        <KeyboardShortcutsOverlay
          open={showShortcuts}
          onOpenChange={setShowShortcuts}
        />
      )}

      {/* Right Sidebar - temporarily hidden when collapsed; LiveDeck remains available for future iteration. */}
      {!isMobile && selectedProjectId && !rightSidebarCollapsed ? (
          <div
            className="relative flex-shrink-0 animate-in slide-in-from-right-2 fade-in duration-200"
            style={{ width: rightSidebarWidth }}
          >
            <ResizeHandle side="right" onResize={handleRightResize} />
            <LiveDeck
              activeTab={liveDeckTab}
              onTabChange={setLiveDeckTab}
              onCollapse={toggleRightSidebar}
              projectId={selectedProjectId}
              runId={selectedRun?.run_id}
              dag={dag}
              onRunSelect={handleRunSelect}
            />
          </div>
      ) : null}
    </div>
  )
}
