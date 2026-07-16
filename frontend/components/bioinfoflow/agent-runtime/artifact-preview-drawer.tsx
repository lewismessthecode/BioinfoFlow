"use client"

import { useEffect, useId, useMemo, useRef, useState, type ReactNode } from "react"
import { AlertCircle, ChevronLeft, FileBox, RotateCw } from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  deliverableArtifacts,
  type AgentRuntimeArtifact,
} from "@/lib/agent-runtime"
import { ArtifactIcon, ArtifactViewer, artifactTypeLabel } from "./artifact-viewers"

export function ArtifactPreviewDrawer({
  artifacts,
  status = "ready",
  error,
  hasSession = true,
  onRetry,
  selectedArtifactId,
  onSelectedArtifactIdChange,
}: {
  artifacts: AgentRuntimeArtifact[]
  status?: "idle" | "loading" | "ready" | "error"
  error?: string | null
  hasSession?: boolean
  onRetry?: () => void
  selectedArtifactId?: string | null
  onSelectedArtifactIdChange?: (artifactId: string | null) => void
}) {
  const t = useTranslations("agentRuntime")
  const [internalSelectedId, setInternalSelectedId] = useState<string | null>(null)
  const selectedBackButtonRef = useRef<HTMLButtonElement>(null)
  const previewArtifacts = useMemo(
    () => deliverableArtifacts(artifacts),
    [artifacts],
  )
  const selectedId =
    selectedArtifactId !== undefined ? selectedArtifactId : internalSelectedId
  const setSelectedId = (artifactId: string | null) => {
    if (onSelectedArtifactIdChange) {
      onSelectedArtifactIdChange(artifactId)
      return
    }
    setInternalSelectedId(artifactId)
  }
  const selected =
    previewArtifacts.find((artifact) => artifact.id === selectedId) ?? null

  useEffect(() => {
    if (!selected) return
    window.requestAnimationFrame(() => selectedBackButtonRef.current?.focus())
  }, [selected])

  if (selected) {
    return (
      <div
        className="grid h-full min-h-0 grid-rows-[auto_minmax(0,1fr)] gap-3"
        data-testid="artifact-preview-drawer"
      >
        <button
          ref={selectedBackButtonRef}
          type="button"
          className="flex w-fit items-center gap-1.5 rounded-md px-1 text-sm font-medium text-foreground transition-colors hover:bg-muted/60"
          onClick={() => setSelectedId(null)}
        >
          <ChevronLeft className="h-4 w-4" />
          {t("artifacts.back")}
        </button>
        <ArtifactViewer artifact={selected} />
      </div>
    )
  }

  if (status === "loading") {
    return (
      <div
        className="grid gap-2"
        data-testid="artifact-preview-drawer"
        role="status"
        aria-live="polite"
        aria-label={t("artifacts.loading")}
      >
        <span className="sr-only">{t("artifacts.loading")}</span>
        {[0, 1, 2].map((index) => (
          <div
            key={index}
            className="h-[62px] animate-pulse rounded-lg border border-border/70 bg-muted/35"
          />
        ))}
      </div>
    )
  }

  if (status === "error") {
    return (
      <ArtifactEmptyState
        icon={<AlertCircle className="h-8 w-8" />}
        title={t("artifacts.loadFailed")}
        description={error || t("artifacts.loadFailedDescription")}
        kind="error"
        action={onRetry ? (
          <Button type="button" size="sm" variant="outline" className="h-8 rounded-md" onClick={onRetry}>
            <RotateCw className="h-3.5 w-3.5" />
            {t("artifacts.retry")}
          </Button>
        ) : null}
      />
    )
  }

  if (!previewArtifacts.length) {
    return (
      <ArtifactEmptyState
        icon={<FileBox className="h-8 w-8" />}
        title={hasSession ? t("artifacts.empty") : t("artifacts.emptyNoSession")}
        description={
          hasSession
            ? t("artifacts.emptyRunningDescription")
            : t("artifacts.emptyNoSessionDescription")
        }
      />
    )
  }

  return (
    <div
      className="grid h-full min-h-0 gap-2 overflow-y-auto pr-1"
      data-testid="artifact-preview-drawer"
    >
      {previewArtifacts.map((artifact) => (
        <button
          key={artifact.id}
          type="button"
          onClick={() => setSelectedId(artifact.id)}
          className="flex w-full items-start gap-3 rounded-lg border border-border/70 bg-card px-3 py-2.5 text-left transition-[background-color,border-color,transform] hover:border-border hover:bg-muted/40 active:scale-[0.99]"
        >
          <ArtifactIcon type={artifact.type} />
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-medium text-foreground">
              {artifact.title}
            </div>
            <div className="truncate text-xs text-muted-foreground">
              {artifact.summary || artifact.file_path || artifactTypeLabel(t, artifact.type)}
            </div>
          </div>
        </button>
      ))}
    </div>
  )
}

function ArtifactEmptyState({
  icon,
  title,
  description,
  kind = "empty",
  action,
}: {
  icon: ReactNode
  title: string
  description: string
  kind?: "empty" | "error"
  action?: ReactNode
}) {
  const titleId = useId()
  const descriptionId = useId()
  return (
    <div
      className="flex h-full min-h-0 items-center justify-center p-6 text-center"
      data-testid="artifact-preview-drawer"
      role={kind === "error" ? "alert" : undefined}
      aria-labelledby={kind === "error" ? titleId : undefined}
      aria-describedby={kind === "error" ? descriptionId : undefined}
    >
      <div className="max-w-[20rem]">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg bg-muted/45 text-muted-foreground">
          {icon}
        </div>
        <p id={titleId} className="mt-3 text-sm font-medium text-foreground">{title}</p>
        {kind === "error" ? (
          <p id={descriptionId} className="mt-1.5 text-xs leading-5 text-muted-foreground">
            {description}
          </p>
        ) : null}
        {action ? <div className="mt-4 flex justify-center">{action}</div> : null}
      </div>
    </div>
  )
}
