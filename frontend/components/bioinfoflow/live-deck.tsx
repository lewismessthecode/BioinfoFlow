"use client"

import { useTranslations } from "next-intl"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { WorkspacePanel } from "./workspace-panel"
import { DagPanel } from "./dag"
import { ChatErrorBoundary } from "./chat/chat-error-boundary"
import { Button } from "@/components/ui/button"
import { PanelRightClose } from "@/lib/icons"
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
  onTabChange: (tab: LiveDeckTab) => void
  onCollapse?: () => void
  projectId?: string | null
  sessionId?: string | null
  selectedArtifactId?: string | null
  onSelectedArtifactIdChange?: (artifactId: string | null) => void
  runId?: string | null
  dag?: DagData | null
  onRunSelect?: (run: Run | null) => void
  workflowName?: string
  adapter?: AgentWorkspaceAdapter
}

export function LiveDeck({
  activeTab,
  onTabChange,
  onCollapse,
  projectId,
  sessionId,
  selectedArtifactId,
  onSelectedArtifactIdChange,
  runId,
  dag,
  onRunSelect,
  workflowName,
  adapter = bioinfoFlowAgentWorkspaceAdapter,
}: LiveDeckProps) {
  const tWorkspace = useTranslations("workspace")
  const tAccessibility = useTranslations("accessibility")

  return (
    <aside className="flex h-full w-full flex-col border-l border-border/70 bg-background/95" role="complementary" aria-label={tWorkspace("liveDeck.label")}>
      <Tabs
        value={activeTab}
        onValueChange={(value) => onTabChange(value as LiveDeckTab)}
        className="flex flex-col h-full"
      >
        <div className="flex min-h-11 items-center gap-1 border-b border-border/60 px-2">
          {onCollapse && (
            <Button
              variant="ghost"
              size="icon"
              className="size-11 shrink-0 rounded-[8px] text-muted-foreground hover:bg-muted/60 hover:text-foreground lg:size-8"
              onClick={onCollapse}
              title={tAccessibility("hidePanel")}
              aria-label={tAccessibility("hidePanel")}
            >
              <PanelRightClose aria-hidden="true" className="h-4 w-4" />
            </Button>
          )}
          <TabsList className="grid h-10 flex-1 grid-cols-4 rounded-none bg-transparent p-0">
            <TabsTrigger
              value="workspace"
              className="h-10 min-w-0 rounded-none border-x-0 border-t-0 border-b-2 border-transparent bg-transparent px-1 text-xs text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none dark:data-[state=active]:bg-transparent"
            >
              {tWorkspace("liveDeck.files")}
            </TabsTrigger>
            <TabsTrigger
              value="dag"
              className="h-10 min-w-0 rounded-none border-x-0 border-t-0 border-b-2 border-transparent bg-transparent px-1 text-xs text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none dark:data-[state=active]:bg-transparent"
            >
              {tWorkspace("liveDeck.pipeline")}
            </TabsTrigger>
            <TabsTrigger
              value="artifacts"
              className="h-10 min-w-0 rounded-none border-x-0 border-t-0 border-b-2 border-transparent bg-transparent px-1 text-xs text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none dark:data-[state=active]:bg-transparent"
            >
              {tWorkspace("liveDeck.artifacts")}
            </TabsTrigger>
            <TabsTrigger
              value="browser"
              className="h-10 min-w-0 rounded-none border-x-0 border-t-0 border-b-2 border-transparent bg-transparent px-1 text-xs text-muted-foreground shadow-none data-[state=active]:border-foreground data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none dark:data-[state=active]:bg-transparent"
            >
              {tWorkspace("liveDeck.browser")}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="workspace" className="flex-1 m-0 overflow-hidden">
          <ChatErrorBoundary label="workspace files">
            <WorkspacePanel projectId={projectId} adapter={adapter} />
          </ChatErrorBoundary>
        </TabsContent>
        <TabsContent value="dag" className="flex-1 m-0 overflow-hidden">
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
        </TabsContent>
        <TabsContent value="artifacts" className="flex-1 m-0 overflow-hidden">
          <ChatErrorBoundary label="agent artifacts">
            <AgentArtifactsPanel
              sessionId={sessionId}
              projectId={projectId}
              adapter={adapter}
              selectedArtifactId={selectedArtifactId}
              onSelectedArtifactIdChange={onSelectedArtifactIdChange}
            />
          </ChatErrorBoundary>
        </TabsContent>
        <TabsContent value="browser" className="flex-1 m-0 overflow-hidden">
          <ChatErrorBoundary label="embedded browser">
            <AgentBrowserPanel />
          </ChatErrorBoundary>
        </TabsContent>
      </Tabs>
    </aside>
  )
}
