"use client"

import { useEffect, useMemo, useState } from "react"
import { Globe, ListChecks, FolderTree, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeEvent,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { BrowserTab } from "./browser-tab"
import { FilesTab } from "./files-tab"
import { PendingDecisionCards } from "./pending-decision-cards"
import { ProgressTab } from "./progress-tab"
import type { AgentDecisionHandler } from "./types"

type AgentTabKey = "progress" | "files" | "browser"

type AgentTabbedPanelProps = {
  projectId?: string | null
  sessionId?: string | null
  events: AgentRuntimeEvent[]
  onClose: () => void
  onDecision: AgentDecisionHandler
  className?: string
}

const TABS: Array<{ key: AgentTabKey; labelKey: string; Icon: typeof ListChecks }> = [
  { key: "progress", labelKey: "tabs.progress", Icon: ListChecks },
  { key: "files", labelKey: "tabs.files", Icon: FolderTree },
  { key: "browser", labelKey: "tabs.browser", Icon: Globe },
]

export function AgentTabbedPanel({
  projectId,
  sessionId,
  events,
  onClose,
  onDecision,
  className,
}: AgentTabbedPanelProps) {
  const t = useTranslations("agentRuntime")
  const [activeTab, setActiveTab] = useState<AgentTabKey>("progress")
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

  return (
    <aside
      className={cn(
        "pointer-events-auto hidden h-full w-[420px] overflow-hidden border-l border-border/70 bg-background lg:flex lg:flex-col",
        className,
      )}
      data-testid="artifact-panel"
    >
      <div className="flex h-12 items-center justify-between border-b border-border/60 px-3">
        <div className="text-sm font-medium text-foreground">{t("sidecar.title")}</div>
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

      {/* Pending approvals / questions are pinned above the tabs so the user
          never has to hunt for an actionable decision. */}
      <div className="border-b border-border/60 px-3 py-2 empty:hidden">
        <PendingDecisionCards events={events} onDecision={onDecision} />
      </div>

      <div className="flex items-center gap-1 border-b border-border/60 px-2 py-1.5">
        {TABS.map(({ key, labelKey, Icon }) => (
          <button
            key={key}
            type="button"
            onClick={() => setActiveTab(key)}
            className={cn(
              "flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors",
              activeTab === key
                ? "bg-muted text-foreground"
                : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
            )}
            data-active={activeTab === key}
          >
            <Icon className="h-3.5 w-3.5" />
            {t(labelKey)}
          </button>
        ))}
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto p-3">
        {activeTab === "progress" ? <ProgressTab artifacts={visibleArtifacts} /> : null}
        {activeTab === "files" ? <FilesTab projectId={projectId} /> : null}
        {activeTab === "browser" ? <BrowserTab /> : null}
      </div>
    </aside>
  )
}
