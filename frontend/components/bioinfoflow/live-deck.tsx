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

export type LiveDeckTab = "workspace" | "dag" | "artifacts" | "browser"

interface LiveDeckProps {
  activeTab: LiveDeckTab
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
  return (
    <aside className="flex h-full w-full flex-col border-l border-border/70 bg-background/95" role="complementary" aria-label={tWorkspace("liveDeck.label")}>
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeTab === "workspace" ? (
          <ChatErrorBoundary label="workspace files">
            <WorkspacePanel
              projectId={projectId}
              adapter={adapter}
              selectedFilePath={selectedFilePath}
              onSelectedFileChange={onSelectedFileChange}
            />
          </ChatErrorBoundary>
        ) : null}
        {activeTab === "dag" ? (
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
        {activeTab === "artifacts" ? (
          <ChatErrorBoundary label="agent artifacts">
            <AgentArtifactsPanel
              sessionId={sessionId}
              projectId={projectId}
              adapter={adapter}
              selectedArtifactId={selectedArtifactId}
              onSelectedArtifactIdChange={onSelectedArtifactIdChange}
            />
          </ChatErrorBoundary>
        ) : null}
        {activeTab === "browser" ? (
          <ChatErrorBoundary label="embedded browser">
            <AgentBrowserPanel />
          </ChatErrorBoundary>
        ) : null}
      </div>
    </aside>
  )
}
