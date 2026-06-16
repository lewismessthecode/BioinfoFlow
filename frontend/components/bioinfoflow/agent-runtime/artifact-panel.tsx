"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import {
  Box,
  ChevronLeft,
  Copy,
  Download,
  FileJson,
  FileText,
  Play,
  TerminalSquare,
  Workflow,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeEvent,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { getPendingActions } from "./pending-actions"

type ArtifactPanelProps = {
  sessionId?: string | null
  events: AgentRuntimeEvent[]
  onClose: () => void
  onDecision: (actionId: string, decision: "approve" | "reject") => void
  className?: string
}

export function ArtifactPanel({
  sessionId,
  events,
  onClose,
  className,
}: ArtifactPanelProps) {
  const t = useTranslations("agentRuntime")
  const pendingActions = useMemo(() => getPendingActions(events), [events])
  const [artifacts, setArtifacts] = useState<AgentRuntimeArtifact[]>([])
  const [selectedId, setSelectedId] = useState<string | null>(null)

  // Refetch the full artifact list whenever a new artifact is created so the
  // panel reflects platform state instead of relying on lightweight events.
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

  // Only show artifacts that belong to the active session; clearing on session
  // change is derived (not a synchronous effect setState).
  const visibleArtifacts = useMemo(
    () => (sessionId ? artifacts : []),
    [sessionId, artifacts],
  )
  const selected = useMemo(
    () => visibleArtifacts.find((artifact) => artifact.id === selectedId) ?? null,
    [visibleArtifacts, selectedId],
  )

  return (
    <aside
      className={cn(
        "pointer-events-auto hidden h-[calc(100%-32px)] w-[380px] overflow-hidden rounded-[26px] border border-border/70 bg-card shadow-2xl shadow-foreground/10 lg:flex lg:flex-col",
        className,
      )}
      data-testid="artifact-panel"
    >
      <div className="flex h-14 items-center justify-between border-b border-border/60 px-4">
        {selected ? (
          <button
            type="button"
            className="flex items-center gap-1.5 text-sm font-medium text-foreground"
            onClick={() => setSelectedId(null)}
          >
            <ChevronLeft className="h-4 w-4" />
            {t("artifacts.back")}
          </button>
        ) : (
          <div className="text-sm font-medium text-foreground">{t("artifacts.title")}</div>
        )}
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

      <div className="min-h-0 flex-1 overflow-y-auto p-4">
        {pendingActions.length > 0 ? (
          <div className="mb-4 rounded-full bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-800 dark:text-amber-200">
            {t("approval.jumpToDecision")}
          </div>
        ) : null}

        {selected ? (
          <ArtifactViewer artifact={selected} />
        ) : visibleArtifacts.length ? (
          <div className="grid gap-2">
            {visibleArtifacts.map((artifact) => (
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
                    {artifact.summary || artifactTypeLabel(t, artifact.type)}
                  </div>
                </div>
              </button>
            ))}
          </div>
        ) : pendingActions.length === 0 ? (
          <p className="text-sm text-muted-foreground">{t("artifacts.empty")}</p>
        ) : null}
      </div>
    </aside>
  )
}

function ArtifactViewer({ artifact }: { artifact: AgentRuntimeArtifact }) {
  switch (artifact.type) {
    case "file":
      return <FileArtifact artifact={artifact} />
    case "command":
    case "log_summary":
      return <CommandArtifact artifact={artifact} />
    case "run":
      return <RecordArtifact artifact={artifact} recordKey="run" />
    case "workflow":
      return <RecordArtifact artifact={artifact} recordKey="workflow" />
    case "image":
      return <RecordArtifact artifact={artifact} recordKey="image" />
    default:
      return <JsonArtifact value={artifact.payload ?? {}} />
  }
}

function FileArtifact({ artifact }: { artifact: AgentRuntimeArtifact }) {
  const t = useTranslations("agentRuntime")
  const payload = artifact.payload ?? {}
  const path = String(payload.path ?? artifact.title)
  const content = typeof payload.content === "string" ? payload.content : ""
  return (
    <div className="grid gap-3">
      <ArtifactHeader title={path} />
      <div className="flex items-center gap-2">
        <CopyButton text={content} label={t("artifacts.copy")} done={t("artifacts.copied")} />
        <DownloadButton
          text={content}
          filename={path.split("/").pop() || "file.txt"}
          label={t("artifacts.download")}
        />
      </div>
      <pre className="max-h-[60vh] overflow-auto rounded-2xl border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
        <code>{content || "—"}</code>
      </pre>
    </div>
  )
}

function CommandArtifact({ artifact }: { artifact: AgentRuntimeArtifact }) {
  const t = useTranslations("agentRuntime")
  const payload = artifact.payload ?? {}
  const command = typeof payload.command === "string" ? payload.command : artifact.title
  const exitCode = payload.exit_code
  const stdout = typeof payload.stdout === "string" ? payload.stdout : ""
  const stderr = typeof payload.stderr === "string" ? payload.stderr : ""
  return (
    <div className="grid gap-3">
      <div className="flex items-center gap-2">
        <span className="rounded-full bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {t("artifacts.exitCode")}: {String(exitCode ?? "?")}
        </span>
      </div>
      <div className="rounded-2xl border border-border/70 bg-foreground/95 p-3 font-mono text-xs leading-5 text-background dark:bg-black/70 dark:text-foreground">
        <div className="mb-2 text-emerald-400">$ {command}</div>
        {stdout ? <pre className="whitespace-pre-wrap break-words">{stdout}</pre> : null}
        {stderr ? (
          <pre className="whitespace-pre-wrap break-words text-red-400">{stderr}</pre>
        ) : null}
        {!stdout && !stderr ? <span className="text-muted-foreground">—</span> : null}
      </div>
    </div>
  )
}

function RecordArtifact({
  artifact,
  recordKey,
}: {
  artifact: AgentRuntimeArtifact
  recordKey: string
}) {
  const payload = artifact.payload ?? {}
  const record =
    payload[recordKey] && typeof payload[recordKey] === "object"
      ? (payload[recordKey] as Record<string, unknown>)
      : payload
  const entries = Object.entries(record).filter(
    ([, value]) => value !== null && value !== undefined && typeof value !== "object",
  )
  return (
    <div className="grid gap-3">
      <ArtifactHeader title={artifact.title} />
      <dl className="grid gap-1.5 rounded-2xl border border-border/70 bg-muted/25 p-3 text-sm">
        {entries.map(([key, value]) => (
          <div key={key} className="flex items-start justify-between gap-3">
            <dt className="text-xs font-medium text-muted-foreground">{key}</dt>
            <dd className="min-w-0 break-words text-right font-mono text-xs text-foreground">
              {String(value)}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}

function JsonArtifact({ value }: { value: unknown }) {
  return (
    <pre className="max-h-[60vh] overflow-auto rounded-2xl border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  )
}

function ArtifactHeader({ title }: { title: string }) {
  return (
    <div className="break-words font-mono text-xs text-muted-foreground">{title}</div>
  )
}

function CopyButton({
  text,
  label,
  done,
}: {
  text: string
  label: string
  done: string
}) {
  const [copied, setCopied] = useState(false)
  const onCopy = useCallback(() => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(true)
      window.setTimeout(() => setCopied(false), 1500)
    })
  }, [text])
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className="h-8 rounded-full bg-card"
      onClick={onCopy}
    >
      <Copy className="h-3.5 w-3.5" />
      {copied ? done : label}
    </Button>
  )
}

function DownloadButton({
  text,
  filename,
  label,
}: {
  text: string
  filename: string
  label: string
}) {
  const onDownload = useCallback(() => {
    const blob = new Blob([text], { type: "text/plain" })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement("a")
    anchor.href = url
    anchor.download = filename
    anchor.click()
    URL.revokeObjectURL(url)
  }, [text, filename])
  return (
    <Button
      type="button"
      size="sm"
      variant="outline"
      className="h-8 rounded-full bg-card"
      onClick={onDownload}
    >
      <Download className="h-3.5 w-3.5" />
      {label}
    </Button>
  )
}

function ArtifactIcon({ type }: { type: string }) {
  const className = "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
  switch (type) {
    case "file":
      return <FileText className={className} />
    case "command":
    case "log_summary":
      return <TerminalSquare className={className} />
    case "run":
      return <Play className={className} />
    case "workflow":
      return <Workflow className={className} />
    case "image":
      return <Box className={className} />
    default:
      return <FileJson className={className} />
  }
}

function artifactTypeLabel(
  t: ReturnType<typeof useTranslations>,
  type: string,
): string {
  const known = ["file", "command", "run", "workflow", "image"]
  if (known.includes(type)) return t(`artifacts.types.${type}`)
  if (type === "log_summary") return t("artifacts.types.command")
  return t("artifacts.types.unknown")
}
