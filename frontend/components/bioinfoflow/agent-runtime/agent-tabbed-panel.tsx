"use client"

import { useEffect, useMemo, useState, type KeyboardEvent } from "react"
import { FileBox, FolderTree, Globe, RotateCw, type LucideIcon, X } from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
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
  hideHeader?: boolean
  className?: string
}

const TABS: Array<{
  key: AgentTabbedPanelTab
  labelKey: string
  iconName: string
  Icon: LucideIcon
}> = [
  { key: "preview", labelKey: "tabs.artifacts", iconName: "file-box", Icon: FileBox },
  { key: "files", labelKey: "tabs.files", iconName: "folder-tree", Icon: FolderTree },
  { key: "browser", labelKey: "tabs.browser", iconName: "globe", Icon: Globe },
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
  hideHeader = false,
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
  const onTabKeyDown = (
    event: KeyboardEvent<HTMLButtonElement>,
    currentIndex: number,
  ) => {
    const lastIndex = TABS.length - 1
    let nextIndex: number | null = null
    switch (event.key) {
      case "ArrowRight":
      case "ArrowDown":
        nextIndex = currentIndex === lastIndex ? 0 : currentIndex + 1
        break
      case "ArrowLeft":
      case "ArrowUp":
        nextIndex = currentIndex === 0 ? lastIndex : currentIndex - 1
        break
      case "Home":
        nextIndex = 0
        break
      case "End":
        nextIndex = lastIndex
        break
      default:
        break
    }
    if (nextIndex === null) return
    event.preventDefault()
    const nextTab = TABS[nextIndex]?.key
    if (!nextTab) return
    onActiveTabChange(nextTab)
    window.requestAnimationFrame(() => {
      document.getElementById(`agent-sidecar-tab-${nextTab}`)?.focus()
    })
  }

  return (
    <aside
      className={cn(
        "pointer-events-auto h-full overflow-hidden border-l border-border/70 bg-background/95",
        variant === "desktop"
          ? "hidden lg:flex lg:w-full lg:flex-col"
          : "flex flex-col",
        className,
      )}
      data-testid="artifact-panel"
    >
      {hideHeader ? null : (
        <div className="flex h-11 min-h-11 items-center justify-between border-b border-border/55 bg-background px-2">
          <div
            className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto"
            role="tablist"
            aria-label={t("sidecar.title")}
            data-testid="agent-sidecar-tab-strip"
          >
            {TABS.map(({ key, labelKey, iconName, Icon }, index) => (
              <Tooltip key={key}>
                <TooltipTrigger asChild>
                  <button
                    type="button"
                    role="tab"
                    id={`agent-sidecar-tab-${key}`}
                    aria-controls={`agent-sidecar-panel-${key}`}
                    aria-selected={activeTab === key}
                    tabIndex={activeTab === key ? 0 : -1}
                    onClick={() => onActiveTabChange(key)}
                    onKeyDown={(event) => onTabKeyDown(event, index)}
                    aria-label={t(labelKey)}
                    className={cn(
                      "flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background",
                      activeTab === key && "bg-muted/60 text-foreground",
                    )}
                    data-active={activeTab === key}
                  >
                    <Icon
                      className="h-4 w-4 shrink-0"
                      data-icon={iconName}
                      data-testid={`agent-sidecar-tab-icon-${key}`}
                      aria-hidden="true"
                    />
                  </button>
                </TooltipTrigger>
                <TooltipContent side="bottom">{t(labelKey)}</TooltipContent>
              </Tooltip>
            ))}
          </div>
          <div className="flex shrink-0 items-center gap-1">
            {activeTab === "preview" && effectiveArtifactStatus === "error" ? (
              <button
                type="button"
                onClick={() => setArtifactReloadNonce((value) => value + 1)}
                aria-label={t("artifacts.retry")}
                className="flex h-8 w-8 items-center justify-center rounded-[8px] text-muted-foreground transition-colors hover:bg-muted/45 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/25 focus-visible:ring-offset-1 focus-visible:ring-offset-background"
              >
                <RotateCw className="h-4 w-4" />
              </button>
            ) : null}
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-8 w-8 rounded-[8px] text-muted-foreground hover:bg-muted/45 hover:text-foreground"
              onClick={onClose}
              aria-label={t("sidecar.close")}
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      )}

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
          activeTab === "browser"
            ? "overflow-y-auto p-3"
            : activeTab === "files"
              ? "overflow-hidden"
              : "overflow-hidden p-3",
        )}
        role="tabpanel"
        id={`agent-sidecar-panel-${activeTab}`}
        aria-labelledby={`agent-sidecar-tab-${activeTab}`}
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
