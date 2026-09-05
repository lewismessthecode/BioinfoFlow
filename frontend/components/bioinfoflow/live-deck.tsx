"use client"

import { useTranslations } from "next-intl"
import { WorkspacePanel, type WorkspaceFileSelection } from "./workspace-panel"
import { DagPanel } from "./dag"
import { ChatErrorBoundary } from "./chat/chat-error-boundary"
import {
  bioinfoFlowAgentWorkspaceAdapter,
  type AgentWorkspaceAdapter,
} from "@/lib/agent/workspace-adapter"
import type { DagData, Run } from "@/lib/types"
import { AgentArtifactsPanel } from "./agent-artifacts-panel"
import { AgentBrowserPanel } from "./agent-browser-panel"
import { Button } from "@/components/ui/button"
import { X } from "@/lib/icons"
import { cn } from "@/lib/utils"
import type { AgentDrawerTab } from "@/lib/agent/drawer-tabs"

export type LiveDeckTab = "workspace" | "dag" | "artifacts" | "browser"

interface LiveDeckProps {
  activeTab: LiveDeckTab
  tabs?: readonly AgentDrawerTab[]
  activeTabId?: string | null
  onSelectTab?: (tabId: string) => void
  onCloseTab?: (tabId: string) => void
  projectId?: string | null
  sessionId?: string | null
  selectedArtifactId?: string | null
  onSelectedArtifactIdChange?: (artifactId: string | null) => void
  runId?: string | null
  dag?: DagData | null
  onRunSelect?: (run: Run | null) => void
  workflowName?: string
  adapter?: AgentWorkspaceAdapter
  selectedFilePath?: string | null
  onSelectedFileChange?: (file: WorkspaceFileSelection | null) => void
}

export function LiveDeck({
  activeTab,
  tabs,
  activeTabId,
  onSelectTab,
  onCloseTab,
  projectId,
  sessionId,
  selectedArtifactId,
  onSelectedArtifactIdChange,
  runId,
  dag,
  onRunSelect,
  workflowName,
  adapter = bioinfoFlowAgentWorkspaceAdapter,
  selectedFilePath,
  onSelectedFileChange,
}: LiveDeckProps) {
  const tWorkspace = useTranslations("workspace")
  const drawerTabs = tabs ?? []
  const activeDrawerTab = drawerTabs.find((tab) => tab.id === activeTabId) ?? null
  const effectiveTab = activeDrawerTab
    ? activeDrawerTab.kind === "file"
      ? "workspace"
      : activeDrawerTab.kind === "artifact"
        ? "artifacts"
        : activeDrawerTab.kind
    : activeTab
  const effectiveSelectedFilePath = activeDrawerTab?.filePath ?? selectedFilePath
  const effectiveSelectedArtifactId = activeDrawerTab?.artifactId ?? selectedArtifactId
  return (
    <aside className="flex h-full w-full flex-col border-l border-border/70 bg-background/95" role="complementary" aria-label={tWorkspace("liveDeck.label")}>
      {drawerTabs.length > 0 ? (
        <div className="flex h-10 shrink-0 items-center gap-1 overflow-x-auto border-b border-border/70 px-2" data-testid="live-deck-tab-bar" role="tablist" aria-label={tWorkspace("liveDeck.label")}>
          {drawerTabs.map((tab) => {
            const active = tab.id === activeTabId
            return (
              <div key={tab.id} className={cn("flex h-7 min-w-0 items-center rounded-md text-xs", active ? "bg-muted text-foreground shadow-sm" : "text-muted-foreground hover:bg-muted/60 hover:text-foreground")}>
                <button type="button" role="tab" aria-selected={active} className="min-w-0 truncate px-2 outline-none focus-visible:ring-2 focus-visible:ring-ring/30" title={tab.title} onClick={() => onSelectTab?.(tab.id)}>{tab.title}</button>
                <Button type="button" variant="ghost" size="icon" className="mr-0.5 size-5 shrink-0 rounded-sm" aria-label={`Close ${tab.title}`} onClick={() => onCloseTab?.(tab.id)}><X aria-hidden="true" className="size-3" /></Button>
              </div>
            )
          })}
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-hidden">
        {tabs !== undefined && drawerTabs.length === 0 ? (
          <div className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground" data-testid="live-deck-empty">
            Open a tab from the + menu.
          </div>
        ) : null}
        {(tabs === undefined || drawerTabs.length > 0) && effectiveTab === "workspace" ? (
          <ChatErrorBoundary label="workspace files">
            <WorkspacePanel
              projectId={projectId}
              adapter={adapter}
              selectedFilePath={effectiveSelectedFilePath}
              onSelectedFileChange={onSelectedFileChange}
            />
          </ChatErrorBoundary>
        ) : null}
        {(tabs === undefined || drawerTabs.length > 0) && effectiveTab === "dag" ? (
          <ChatErrorBoundary label="pipeline DAG">
            <DagPanel
              projectId={projectId}
              runId={runId}
              dag={dag}
              showRunSelector={true}
              onRunSelect={onRunSelect}
              workflowName={workflowName}
            />
          </ChatErrorBoundary>
        ) : null}
        {(tabs === undefined || drawerTabs.length > 0) && effectiveTab === "artifacts" ? (
          <ChatErrorBoundary label="agent artifacts">
            <AgentArtifactsPanel
              sessionId={sessionId}
              projectId={projectId}
              adapter={adapter}
              selectedArtifactId={effectiveSelectedArtifactId}
              onSelectedArtifactIdChange={onSelectedArtifactIdChange}
            />
          </ChatErrorBoundary>
        ) : null}
        {(tabs === undefined || drawerTabs.length > 0) && effectiveTab === "browser" ? (
          <ChatErrorBoundary label="embedded browser">
            <AgentBrowserPanel />
          </ChatErrorBoundary>
        ) : null}
      </div>
    </aside>
  )
}
