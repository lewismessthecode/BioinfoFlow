"use client"

import { useEffect, useMemo, useState } from "react"
import { FileSearch, FolderTree, Globe, RotateCw, type LucideIcon, X } from "lucide-react"
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
  variant?: "desktop" | "mobile"
  className?: string
}

const TABS: Array<{ key: AgentTabbedPanelTab; labelKey: string; Icon: LucideIcon }> = [
  { key: "preview", labelKey: "tabs.artifacts", Icon: FileSearch },
  { key: "files", labelKey: "tabs.files", Icon: FolderTree },
  { key: "browser", labelKey: "tabs.browser", Icon: Globe },
]

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
  variant = "desktop",
  className,
}: AgentTabbedPanelProps) {
  const t = useTranslations("agentRuntime")
  const [artifactReloadNonce, setArtifactReloadNonce] = useState(0)
  const [artifactLoadState, setArtifactLoadState] = useState<{
    requestKey: string
    status: "ready" | "error"
    artifacts: AgentRuntimeArtifact[]
    error: string | null
  }>({
    requestKey: "",
    status: "ready",
    artifacts: [],
    error: null,
  })
  const artifactLoadFailed = t("artifacts.loadFailed")

  const artifactEventCount = useMemo(
    () => events.filter((event) => event.type === "artifact.created").length,
    [events],
  )
  const artifactRequestKey = sessionId
    ? `${sessionId}:${artifactEventCount}:${artifactReloadNonce}`
    : ""

  useEffect(() => {
    if (!sessionId) return
    let cancelled = false
    void listAgentRuntimeSessionArtifacts(sessionId)
      .then((next) => {
        if (!cancelled) {
          setArtifactLoadState({
            requestKey: artifactRequestKey,
            status: "ready",
            artifacts: next,
            error: null,
          })
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setArtifactLoadState({
            requestKey: artifactRequestKey,
            status: "error",
            artifacts: [],
            error: err instanceof Error ? err.message : artifactLoadFailed,
          })
        }
      })
    return () => {
      cancelled = true
    }
  }, [artifactLoadFailed, artifactRequestKey, sessionId])

  const artifactStateMatchesRequest = artifactLoadState.requestKey === artifactRequestKey
  const visibleArtifacts = useMemo(
    () =>
      sessionId && artifactStateMatchesRequest && artifactLoadState.status === "ready"
        ? deliverableArtifacts(artifactLoadState.artifacts)
        : [],
    [artifactLoadState.artifacts, artifactLoadState.status, artifactStateMatchesRequest, sessionId],
  )
  const effectiveArtifactStatus = !sessionId
    ? "idle"
    : artifactStateMatchesRequest
      ? artifactLoadState.status
      : "loading"
  const effectiveArtifactError =
    sessionId && artifactStateMatchesRequest ? artifactLoadState.error : null
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
        "pointer-events-auto h-full overflow-hidden border-l border-border/70 bg-background",
        variant === "desktop"
          ? "hidden lg:flex lg:w-full lg:flex-col"
          : "flex flex-col",
        className,
      )}
      data-testid="artifact-panel"
    >
      <div className="flex h-[52px] min-h-[52px] items-center justify-between border-b border-border/60 px-3">
        <div className="min-w-0">
          <div className="truncate text-sm font-semibold text-foreground">
            {activeTab === "preview"
              ? t("artifacts.title")
              : activeTab === "files"
                ? t("files.title")
                : t("browser.title")}
          </div>
          <div className="truncate text-[11px] text-muted-foreground">
            {activeTab === "preview"
              ? t("artifacts.count", { count: visibleArtifacts.length })
              : t("sidecar.title")}
          </div>
        </div>
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
          {activeTab === "preview" && effectiveArtifactStatus === "error" ? (
            <button
              type="button"
              onClick={() => setArtifactReloadNonce((value) => value + 1)}
              aria-label={t("artifacts.retry")}
              className="flex h-8 w-8 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted/50 hover:text-foreground"
            >
              <RotateCw className="h-4 w-4" />
            </button>
          ) : null}
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
        {activeTab === "preview" ? (
          <ArtifactPreviewDrawer
            artifacts={visibleArtifacts}
            status={effectiveArtifactStatus}
            error={effectiveArtifactError}
            hasSession={Boolean(sessionId)}
            onRetry={() => setArtifactReloadNonce((value) => value + 1)}
          />
        ) : null}
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
