"use client"

import { useEffect, useMemo, useState } from "react"
import { Eye, FolderTree, Globe, X } from "lucide-react"
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

type AgentSideDrawerTab = "preview" | "files" | "browser"

type AgentSideDrawerProps = {
  projectId?: string | null
  sessionId?: string | null
  events: AgentRuntimeEvent[]
  onClose: () => void
  onAddContext?: (path: string) => void
  className?: string
}

const TABS: Array<{ key: AgentSideDrawerTab; labelKey: string; Icon: typeof Eye }> = [
  { key: "preview", labelKey: "tabs.preview", Icon: Eye },
  { key: "files", labelKey: "tabs.files", Icon: FolderTree },
  { key: "browser", labelKey: "tabs.browser", Icon: Globe },
]

export function AgentSideDrawer({
  projectId,
  sessionId,
  events,
  onClose,
  onAddContext,
  className,
}: AgentSideDrawerProps) {
  const t = useTranslations("agentRuntime")
  const [activeTab, setActiveTab] = useState<AgentSideDrawerTab>("preview")
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

  const visibleArtifacts = sessionId ? artifacts : []
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
        "pointer-events-auto hidden h-full w-[420px] overflow-hidden border-l border-border/70 bg-background lg:flex lg:flex-col",
        className,
      )}
      data-testid="artifact-panel"
    >
      <div className="flex h-12 items-center justify-between border-b border-border/60 px-2">
        <div className="flex items-center gap-1">
          {TABS.map(({ key, labelKey, Icon }) => (
            <button
              key={key}
              type="button"
              onClick={() => setActiveTab(key)}
              aria-label={t(labelKey)}
              className={cn(
                "flex h-8 w-8 items-center justify-center rounded-full transition-colors",
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
          className="h-8 w-8 rounded-full text-muted-foreground hover:bg-muted hover:text-foreground"
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

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {activeTab === "preview" ? <ArtifactPreviewDrawer artifacts={visibleArtifacts} /> : null}
        {activeTab === "files" ? (
          <WorkspaceExplorerPanel projectId={projectId} onAddContext={onAddContext} />
        ) : null}
        {activeTab === "browser" ? <BrowserTab /> : null}
      </div>
    </aside>
  )
}
