"use client"

import { useTranslations } from "next-intl"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { FolderOpen, GitBranch, Activity, PanelRightClose } from "lucide-react"
import { WorkspacePanel } from "./workspace-panel"
import { DagPanel } from "./dag"
import { MonitorPanel } from "./monitor-panel"
import { ChatErrorBoundary } from "./chat/chat-error-boundary"
import { Button } from "@/components/ui/button"
import type { DagData, Run } from "@/lib/types"

interface LiveDeckProps {
  activeTab: "workspace" | "dag" | "monitor"
  onTabChange: (tab: "workspace" | "dag" | "monitor") => void
  onCollapse?: () => void
  projectId?: string | null
  runId?: string | null
  dag?: DagData | null
  onRunSelect?: (run: Run | null) => void
  workflowName?: string
}

export function LiveDeck({
  activeTab,
  onTabChange,
  onCollapse,
  projectId,
  runId,
  dag,
  onRunSelect,
  workflowName,
}: LiveDeckProps) {
  const tWorkspace = useTranslations("workspace")
  const tAccessibility = useTranslations("accessibility")

  return (
    <aside className="w-full h-full border-l border-border bg-background flex flex-col" role="complementary" aria-label="Live information panel">
      <Tabs
        value={activeTab}
        onValueChange={(v) => onTabChange(v as "workspace" | "dag" | "monitor")}
        className="flex flex-col h-full"
      >
        <div className="border-b border-border px-2 pt-2 pb-0 flex items-center gap-2">
          {onCollapse && (
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-foreground shrink-0"
              onClick={onCollapse}
              title={tAccessibility("hidePanel")}
              aria-label={tAccessibility("hidePanel")}
            >
              <PanelRightClose className="h-4 w-4" />
            </Button>
          )}
          <TabsList className="flex-1 grid grid-cols-3 bg-secondary/50 p-1 h-auto">
            <TabsTrigger
              value="workspace"
              className="gap-1.5 text-xs py-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
            >
              <FolderOpen className="h-3.5 w-3.5" />
              {tWorkspace("liveDeck.files")}
            </TabsTrigger>
            <TabsTrigger
              value="dag"
              className="gap-1.5 text-xs py-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
            >
              <GitBranch className="h-3.5 w-3.5" />
              {tWorkspace("liveDeck.pipeline")}
            </TabsTrigger>
            <TabsTrigger
              value="monitor"
              className="gap-1.5 text-xs py-2 data-[state=active]:bg-background data-[state=active]:shadow-sm"
            >
              <Activity className="h-3.5 w-3.5" />
              {tWorkspace("liveDeck.monitor")}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent value="workspace" className="flex-1 m-0 overflow-hidden">
          <WorkspacePanel />
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
        <TabsContent value="monitor" className="flex-1 m-0 overflow-hidden">
          <MonitorPanel />
        </TabsContent>
      </Tabs>
    </aside>
  )
}
