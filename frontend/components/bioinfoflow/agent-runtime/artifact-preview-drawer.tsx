"use client"

import { useMemo, useState } from "react"
import { ChevronLeft } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"
import { ArtifactIcon, ArtifactViewer, artifactTypeLabel } from "./artifact-viewers"

export function ArtifactPreviewDrawer({ artifacts }: { artifacts: AgentRuntimeArtifact[] }) {
  const t = useTranslations("agentRuntime")
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const previewArtifacts = useMemo(
    () => artifacts.filter(isPreviewArtifact),
    [artifacts],
  )
  const selected = previewArtifacts.find((artifact) => artifact.id === selectedId) ?? null

  if (selected) {
    return (
      <div className="grid gap-3" data-testid="artifact-preview-drawer">
        <button
          type="button"
          className="flex w-fit items-center gap-1.5 text-sm font-medium text-foreground"
          onClick={() => setSelectedId(null)}
        >
          <ChevronLeft className="h-4 w-4" />
          {t("artifacts.back")}
        </button>
        <ArtifactViewer artifact={selected} />
      </div>
    )
  }

  if (!previewArtifacts.length) {
    return (
      <p className="text-sm text-muted-foreground" data-testid="artifact-preview-drawer">
        {t("artifacts.empty")}
      </p>
    )
  }

  return (
    <div className="grid gap-2" data-testid="artifact-preview-drawer">
      {previewArtifacts.map((artifact) => (
        <button
          key={artifact.id}
          type="button"
          onClick={() => setSelectedId(artifact.id)}
          className="flex w-full items-start gap-3 rounded-2xl border border-border/70 bg-card px-3 py-2.5 text-left transition-colors hover:border-border hover:bg-muted/40"
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

const HIDDEN_ARTIFACT_TYPES = new Set(["command", "log_summary", "todo_list"])
const PREVIEW_ARTIFACT_TYPES = new Set([
  "file",
  "html",
  "image",
  "pdf",
  "project",
  "report",
  "run",
  "sheet",
  "spreadsheet",
  "workflow",
  "workflow_bundle",
])

function isPreviewArtifact(artifact: AgentRuntimeArtifact) {
  if (HIDDEN_ARTIFACT_TYPES.has(artifact.type)) return false
  if (artifact.file_path || artifact.resource_ref) return true
  return PREVIEW_ARTIFACT_TYPES.has(artifact.type)
}
