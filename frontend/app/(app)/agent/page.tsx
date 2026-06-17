"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import {
  AgentWorkbench,
  type AgentWorkbenchHandle,
} from "@/components/bioinfoflow/agent-runtime/agent-workbench"
import { LiveDeck } from "@/components/bioinfoflow/live-deck"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { useEvents } from "@/hooks/use-events"
import type { DagData, Run } from "@/lib/types"
import { ResizeHandle } from "@/components/ui/resize-handle"
import { useIsMobile } from "@/hooks/use-media-query"
import { KeyboardShortcutsOverlay } from "@/components/bioinfoflow/chat/keyboard-shortcuts-overlay"

const RIGHT_SIDEBAR_MIN = 300
const RIGHT_SIDEBAR_MAX = 600
const RIGHT_SIDEBAR_DEFAULT = 400

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
  const chatRef = useRef<AgentWorkbenchHandle>(null)
  const { setActiveConversationId } = useProjectContext()
  const [liveDeckTab, setLiveDeckTab] = useState<"workspace" | "dag" | "monitor">("workspace")
  const [rightSidebarWidth, setRightSidebarWidth] = useState(RIGHT_SIDEBAR_DEFAULT)
  const [rightSidebarCollapsed, setRightSidebarCollapsed] = useState(true)
  const [selectedRun, setSelectedRun] = useState<Run | null>(null)
  const [dag, setDag] = useState<DagData | null>(null)

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
    <div className="flex h-full min-w-0 overflow-hidden bg-background">
      <AgentWorkbench
        ref={chatRef}
        projectId={conversationProjectId || null}
        activeSessionId={activeConversationId}
        onActiveSessionIdChange={setActiveConversationId}
        workspaceEnabled
        className="min-w-0 flex-1"
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
