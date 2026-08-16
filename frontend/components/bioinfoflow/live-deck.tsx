"use client"

import { useTranslations } from "next-intl"
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs"
import { FolderOpen, GitBranch, PanelRightClose } from "@/lib/icons"
import { WorkspacePanel } from "./workspace-panel"
import { DagPanel } from "./dag"
import { ChatErrorBoundary } from "./chat/chat-error-boundary"
import { Button } from "@/components/ui/button"
import type { DagData, Run } from "@/lib/types"

interface LiveDeckProps {
  activeTab: "workspace" | "dag"
  onTabChange: (tab: "workspace" | "dag") => void
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
    <aside className="flex h-full w-full flex-col border-l border-border/70 bg-background/95" role="complementary" aria-label={tWorkspace("liveDeck.label")}>
      <Tabs
        value={activeTab}
        onValueChange={(v) => onTabChange(v as "workspace" | "dag")}
        className="flex flex-col h-full"
      >
        <div className="flex min-h-11 items-center gap-2 border-b border-border/60 px-2.5">
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
          <TabsList className="grid h-8 flex-1 grid-cols-2 rounded-[8px] bg-muted/55 p-0.5">
            <TabsTrigger
              value="workspace"
              className="min-h-11 gap-1.5 rounded-[6px] py-1.5 text-xs data-[state=active]:bg-background data-[state=active]:shadow-none lg:min-h-0"
            >
              <FolderOpen aria-hidden="true" className="h-3.5 w-3.5" />
              {tWorkspace("liveDeck.files")}
            </TabsTrigger>
            <TabsTrigger
              value="dag"
              className="min-h-11 gap-1.5 rounded-[6px] py-1.5 text-xs data-[state=active]:bg-background data-[state=active]:shadow-none lg:min-h-0"
            >
              <GitBranch aria-hidden="true" className="h-3.5 w-3.5" />
              {tWorkspace("liveDeck.pipeline")}
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
      </Tabs>
    </aside>
  )
}
