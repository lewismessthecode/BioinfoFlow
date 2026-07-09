"use client"

import { useEffect, useMemo, useState } from "react"
import Link from "next/link"
import {
  FileSearch,
  FolderTree,
  Globe,
  ListChecks,
  type LucideIcon,
  Play,
  Workflow,
  X,
} from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  decisionScrollTargetId,
  deliverableArtifacts,
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeEvent,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { ArtifactPreviewDrawer } from "./artifact-preview-drawer"
import { BrowserTab } from "./browser-tab"
import { getPendingActions } from "./pending-actions"
import { WorkspaceExplorerPanel } from "./workspace-explorer-panel"

type AgentSideDrawerTab = "tools" | "preview" | "files" | "browser"

type AgentSideDrawerProps = {
  projectId?: string | null
  sessionId?: string | null
  events: AgentRuntimeEvent[]
  onClose: () => void
  onAddContext?: (path: string) => void
  className?: string
}

const TABS: Array<{ key: AgentSideDrawerTab; labelKey: string; Icon: LucideIcon }> = [
  { key: "tools", labelKey: "tabs.tools", Icon: ListChecks },
  { key: "preview", labelKey: "tabs.preview", Icon: FileSearch },
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
  const [activeTab, setActiveTab] = useState<AgentSideDrawerTab>("tools")
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
    () => (sessionId ? deliverableArtifacts(artifacts) : []),
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
              onClick={() => setActiveTab(key)}
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
            className="w-full rounded-[8px] border border-foreground/10 bg-foreground/[0.045] px-3 py-1.5 text-left text-xs font-medium text-foreground/72 hover:bg-foreground/[0.07] dark:border-border dark:bg-muted/35 dark:text-foreground/76"
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
        {activeTab === "tools" ? (
          <AgentToolsPanel
            artifactCount={visibleArtifacts.length}
            onOpenPreview={() => setActiveTab("preview")}
            onOpenFiles={() => setActiveTab("files")}
            onOpenBrowser={() => setActiveTab("browser")}
          />
        ) : null}
        {activeTab === "preview" ? <ArtifactPreviewDrawer artifacts={visibleArtifacts} /> : null}
        {activeTab === "files" ? (
          <WorkspaceExplorerPanel projectId={projectId} onAddContext={onAddContext} />
        ) : null}
        {activeTab === "browser" ? <BrowserTab /> : null}
      </div>
    </aside>
  )
}

function AgentToolsPanel({
  artifactCount,
  onOpenPreview,
  onOpenFiles,
  onOpenBrowser,
}: {
  artifactCount: number
  onOpenPreview: () => void
  onOpenFiles: () => void
  onOpenBrowser: () => void
}) {
  const t = useTranslations("agentRuntime")

  return (
    <div className="flex min-h-full flex-col justify-center gap-3 py-8" data-testid="agent-tools-panel">
      <div className="mb-1 px-1">
        <h2 className="text-sm font-semibold tracking-tight text-foreground">
          {t("toolsPanel.title")}
        </h2>
        <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
          {t("toolsPanel.description")}
        </p>
      </div>
      <div className="grid gap-2">
        <ToolButton
          label={t("toolsPanel.review")}
          description={
            artifactCount > 0
              ? t("toolsPanel.artifactCount", { count: artifactCount })
              : t("toolsPanel.noArtifacts")
          }
          Icon={FileSearch}
          onClick={onOpenPreview}
        />
        <ToolButton
          label={t("toolsPanel.browser")}
          description={t("toolsPanel.browserDescription")}
          Icon={Globe}
          onClick={onOpenBrowser}
        />
        <ToolButton
          label={t("toolsPanel.files")}
          description={t("toolsPanel.filesDescription")}
          Icon={FolderTree}
          onClick={onOpenFiles}
        />
        <ToolLink
          href="/workflows"
          label={t("toolsPanel.workflows")}
          description={t("toolsPanel.workflowsDescription")}
          Icon={Workflow}
        />
        <ToolLink
          href="/runs"
          label={t("toolsPanel.runs")}
          description={t("toolsPanel.runsDescription")}
          Icon={Play}
        />
      </div>
    </div>
  )
}

function ToolButton({
  label,
  description,
  shortcut,
  Icon,
  onClick,
}: {
  label: string
  description: string
  shortcut?: string
  Icon: LucideIcon
  onClick: () => void
}) {
  return (
    <button
      type="button"
      className="group flex min-h-12 w-full items-center gap-3 rounded-lg bg-muted/70 px-3 py-2 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
      onClick={onClick}
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-foreground">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{description}</span>
      </span>
      {shortcut ? (
        <kbd className="rounded-md border border-border bg-background px-1.5 py-0.5 font-mono text-[10px] font-medium text-muted-foreground">
          {shortcut}
        </kbd>
      ) : null}
    </button>
  )
}

function ToolLink({
  href,
  label,
  description,
  Icon,
}: {
  href: string
  label: string
  description: string
  Icon: LucideIcon
}) {
  return (
    <Link
      href={href}
      className="group flex min-h-12 w-full items-center gap-3 rounded-lg bg-muted/70 px-3 py-2 text-left transition-colors hover:bg-muted focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/35"
    >
      <Icon className="h-4 w-4 shrink-0 text-muted-foreground transition-colors group-hover:text-foreground" />
      <span className="min-w-0">
        <span className="block truncate text-sm font-semibold text-foreground">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{description}</span>
      </span>
    </Link>
  )
}
