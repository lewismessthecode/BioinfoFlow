"use client"

import { useEffect, useMemo, useState } from "react"
import { FileSearch, FolderTree, Globe, type LucideIcon, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  decisionScrollTargetId,
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeEvent,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ArtifactPreviewDrawer } from "./artifact-preview-drawer"
import { BrowserTab } from "./browser-tab"
import { getPendingActions } from "./pending-actions"
import { WorkspaceExplorerPanel } from "./workspace-explorer-panel"

export type AgentTabbedPanelTab = "files" | "preview" | "browser"

type AgentTabbedPanelProps = {
  projectId?: string | null
  sessionId?: string | null
  events: AgentRuntimeEvent[]
  activeTab: AgentTabbedPanelTab
  onActiveTabChange: (tab: AgentTabbedPanelTab) => void
  browserInput: string
  browserSrc: string
  onBrowserInputChange: (value: string) => void
  onBrowserSrcChange: (value: string) => void
  onClose: () => void
  onAddContext?: (path: string) => void
  className?: string
}

const TABS: Array<{ key: AgentTabbedPanelTab; labelKey: string; Icon: LucideIcon }> = [
  { key: "files", labelKey: "tabs.files", Icon: FolderTree },
  { key: "preview", labelKey: "tabs.preview", Icon: FileSearch },
  { key: "browser", labelKey: "tabs.browser", Icon: Globe },
]

const DELIVERABLE_ARTIFACT_TYPES = new Set([
  "file",
  "html",
  "pdf",
  "report",
  "markdown",
  "sheet",
  "spreadsheet",
])

export function AgentTabbedPanel({
  projectId,
  sessionId,
  events,
  activeTab,
  onActiveTabChange,
  browserInput,
  browserSrc,
  onBrowserInputChange,
  onBrowserSrcChange,
  onClose,
  onAddContext,
  className,
}: AgentTabbedPanelProps) {
  const t = useTranslations("agentRuntime")
  const [artifacts, setArtifacts] = useState<AgentRuntimeArtifact[]>([])

  const artifactEventCount = useMemo(
    () => events.filter((event) => event.type === "artifact.created").length,
    [events],
  )

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    void listAgentRuntimeSessionArtifacts(sessionId)
      .then((next) => {
        if (!cancelled) setArtifacts(next)
      })
      .catch(() => {
        if (!cancelled) setArtifacts([])
      })
    return () => {
      cancelled = true
    }
  }, [sessionId, artifactEventCount])

  const visibleArtifacts = useMemo(
    () => (sessionId ? artifacts.filter(isDeliverableArtifact) : []),
    [artifacts, sessionId],
  )
  const pendingDecision = useMemo(() => getPendingActions(events)[0] ?? null, [events])
  const pendingDecisionActionId = pendingDecision
    ? String(pendingDecision.payload.action_id || "")
    : null
  const jumpToPendingDecision = () => {
    if (!pendingDecisionActionId) return
    document.getElementById(decisionScrollTargetId(pendingDecisionActionId))?.scrollIntoView({
      block: "center",
      behavior: "smooth",
    })
  }

  return (
    <aside
      className={cn(
        "pointer-events-auto hidden h-full overflow-hidden border-l border-border/70 bg-background lg:flex lg:flex-col",
        "lg:w-[clamp(360px,32vw,500px)]",
        className,
      )}
      data-testid="artifact-panel"
    >
      <div className="flex h-12 items-center justify-between border-b border-border/60 px-3">
        <div className="flex items-center gap-1">
          {TABS.map(({ key, labelKey, Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => onActiveTabChange(key)}
              aria-label={t(labelKey)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-lg transition-colors",
                activeTab === key
                  ? "bg-muted text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
              )}
              data-active={activeTab === key}
            >
              <Icon className="h-4 w-4" />
            </button>
          ))}
        </div>
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
          onClick={onClose}
          aria-label={t("sidecar.close")}
        >
          <X className="h-4 w-4" />
        </Button>
      </div>

      {pendingDecisionActionId ? (
        <div className="border-b border-border/60 px-3 py-2" data-testid="sidecar-decision-indicator">
          <button
            type="button"
            className="w-full rounded-full bg-amber-500/10 px-3 py-1.5 text-left text-xs font-medium text-amber-800 hover:bg-amber-500/15 dark:text-amber-200"
            onClick={jumpToPendingDecision}
          >
            {t("approval.jumpToDecision")}
          </button>
        </div>
      ) : null}

      <div
        className={cn(
          "min-h-0 flex-1",
          activeTab === "files" ? "overflow-hidden p-3" : "overflow-y-auto p-3",
        )}
      >
        {activeTab === "files" ? (
          <WorkspaceExplorerPanel projectId={projectId} onAddContext={onAddContext} />
        ) : null}
        {activeTab === "preview" ? <ArtifactPreviewDrawer artifacts={visibleArtifacts} /> : null}
        {activeTab === "browser" ? (
          <BrowserTab
            input={browserInput}
            src={browserSrc}
            onInputChange={onBrowserInputChange}
            onSrcChange={onBrowserSrcChange}
          />
        ) : null}
      </div>
    </aside>
  )
}

function isDeliverableArtifact(artifact: AgentRuntimeArtifact) {
  if (artifact.type === "command" || artifact.type === "log_summary" || artifact.type === "todo_list") {
    return false
  }
  if (artifact.file_path) return true
  return DELIVERABLE_ARTIFACT_TYPES.has(artifact.type)
}
