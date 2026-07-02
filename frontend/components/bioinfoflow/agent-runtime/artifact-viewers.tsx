"use client"

import { useCallback, useState } from "react"
import {
  Box,
  Copy,
  Download,
  ExternalLink,
  FileCode,
  FileJson,
  FileSpreadsheet,
  FileText,
  ListChecks,
  Play,
  TerminalSquare,
  Workflow,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  buildAgentFsDownloadUrl,
  type AgentRuntimeArtifact,
  type AgentTodoItem,
} from "@/lib/agent-runtime"
import { TodoChecklist } from "./todo-checklist"
import { UniversalFileRenderer } from "./universal-file-renderer"

export function ArtifactViewer({ artifact }: { artifact: AgentRuntimeArtifact }) {
  if (artifact.file_path) return <FileArtifact artifact={artifact} />

  switch (artifact.type) {
    case "file":
    case "html":
    case "image":
    case "markdown":
    case "pdf":
    case "report":
    case "sheet":
    case "spreadsheet":
      return <FileArtifact artifact={artifact} />
    case "command":
    case "log_summary":
      return <CommandArtifact artifact={artifact} />
    case "todo_list":
      return <TodoChecklist todos={todosFromArtifact(artifact)} />
    case "run":
      return <RecordArtifact artifact={artifact} recordKey="run" />
    case "workflow":
      return <RecordArtifact artifact={artifact} recordKey="workflow" />
    default:
      return <JsonArtifact value={artifact.payload ?? {}} />
  }
}

export function todosFromArtifact(artifact: AgentRuntimeArtifact): AgentTodoItem[] {
  const todos = artifact.payload?.todos
  return Array.isArray(todos) ? (todos as AgentTodoItem[]) : []
}

function FileArtifact({ artifact }: { artifact: AgentRuntimeArtifact }) {
  const t = useTranslations("agentRuntime")
  const payload = artifact.payload ?? {}
  const path = String(payload.path ?? artifact.file_path ?? artifact.title)
  const content = typeof payload.content === "string" ? payload.content : ""
  const filename = path.split("/").pop() || artifact.title || "artifact.txt"
  const resourceUrl = sanitizeArtifactResourceUrl(artifactResourceUrl(artifact))
  const fileDownloadUrl = artifact.file_path ? buildAgentFsDownloadUrl(artifact.file_path) : null
  const fileInlineUrl = artifact.file_path
    ? buildAgentFsDownloadUrl(artifact.file_path, { inline: true })
    : null
  const openUrl = resourceUrl || fileDownloadUrl
  const canCopyOrDownload = content.length > 0
  const canDownloadInlineContent = canCopyOrDownload && !openUrl

  return (
    <div className="grid h-full min-h-0 grid-rows-[auto_auto_minmax(0,1fr)] gap-3" data-testid="artifact-file-viewer">
      <ArtifactHeader title={path} />
      {canCopyOrDownload || openUrl ? (
        <div className="flex flex-wrap items-center gap-2">
          {canCopyOrDownload ? (
            <CopyButton text={content} label={t("artifacts.copy")} done={t("artifacts.copied")} />
          ) : null}
          {canDownloadInlineContent ? (
            <DownloadButton
              text={content}
              filename={filename}
              label={t("artifacts.download")}
            />
          ) : null}
          {openUrl ? (
            <>
              <LinkButton href={openUrl} label={t("artifacts.open")} icon="open" />
              <LinkButton href={openUrl} label={t("artifacts.download")} icon="download" />
            </>
          ) : null}
        </div>
      ) : null}
      <div className="min-h-0 overflow-hidden rounded-lg border border-border/70 bg-background">
        <UniversalFileRenderer
          file={{
            path,
            title: filename,
            type: artifact.type,
            content,
            rows: payload.rows,
            size: numberValue(payload.size),
            language: stringValue(payload.language) ?? stringValue(payload.lang),
            mimeType: stringValue(payload.mime_type),
            binary: booleanValue(payload.binary),
            inlineUrl: resourceUrl || fileInlineUrl,
            downloadUrl: fileDownloadUrl,
            resourceUrl,
          }}
        />
      </div>
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
        <span className="rounded-md bg-muted px-2 py-0.5 text-xs font-medium text-muted-foreground">
          {t("artifacts.exitCode")}: {String(exitCode ?? "?")}
        </span>
      </div>
      <div className="rounded-lg border border-border/70 bg-foreground/95 p-3 font-mono text-xs leading-5 text-background dark:bg-black/70 dark:text-foreground">
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
      <dl className="grid gap-1.5 rounded-lg border border-border/70 bg-muted/25 p-3 text-sm">
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
    <pre className="max-h-[60vh] overflow-auto rounded-lg border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
      <code>{JSON.stringify(value, null, 2)}</code>
    </pre>
  )
}

function ArtifactHeader({ title }: { title: string }) {
  return (
    <div className="break-words font-mono text-xs text-muted-foreground">{title}</div>
  )
}

function CopyButton({ text, label, done }: { text: string; label: string; done: string }) {
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
      className="h-8 rounded-md bg-card transition-transform active:scale-[0.98]"
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
      className="h-8 rounded-md bg-card transition-transform active:scale-[0.98]"
      onClick={onDownload}
    >
      <Download className="h-3.5 w-3.5" />
      {label}
    </Button>
  )
}

function LinkButton({
  href,
  label,
  icon,
}: {
  href: string
  label: string
  icon: "download" | "open"
}) {
  const Icon = icon === "download" ? Download : ExternalLink
  return (
    <Button
      size="sm"
      variant="outline"
      className="h-8 rounded-md bg-card transition-transform active:scale-[0.98]"
      asChild
    >
      <a
        href={href}
        target={icon === "open" ? "_blank" : undefined}
        rel="noreferrer"
        download={icon === "download" ? "" : undefined}
      >
        <Icon className="h-3.5 w-3.5" />
        {label}
      </a>
    </Button>
  )
}

export function ArtifactIcon({ type }: { type: string }) {
  const className = "mt-0.5 h-4 w-4 shrink-0 text-muted-foreground"
  switch (type) {
    case "html":
      return <FileCode className={className} />
    case "sheet":
    case "spreadsheet":
      return <FileSpreadsheet className={className} />
    case "file":
    case "markdown":
    case "pdf":
    case "report":
      return <FileText className={className} />
    case "command":
    case "log_summary":
      return <TerminalSquare className={className} />
    case "todo_list":
      return <ListChecks className={className} />
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

export function artifactTypeLabel(
  t: ReturnType<typeof useTranslations>,
  type: string,
): string {
  const known = [
    "file",
    "command",
    "html",
    "image",
    "markdown",
    "pdf",
    "run",
    "sheet",
    "spreadsheet",
    "workflow",
  ]
  if (known.includes(type)) return t(`artifacts.types.${type}`)
  if (type === "log_summary") return t("artifacts.types.command")
  if (type === "todo_list") return t("artifacts.types.todo_list")
  return t("artifacts.types.unknown")
}

function artifactResourceUrl(artifact: AgentRuntimeArtifact) {
  const payload = artifact.payload ?? {}
  const payloadUrl = stringValue(payload.url) ?? stringValue(payload.href)
  if (payloadUrl) return payloadUrl
  const resource = artifact.resource_ref
  if (!resource || typeof resource !== "object") return null
  return stringValue(resource.url) ?? stringValue(resource.href)
}

function sanitizeArtifactResourceUrl(url: string | null) {
  if (!url) return null
  try {
    const base = typeof window !== "undefined" ? window.location.href : "http://localhost"
    const parsed = new URL(url, base)
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") return null

    const isRelativePath = url.startsWith("/") && !url.startsWith("//")
    if (isRelativePath) {
      return parsed.pathname.startsWith("/api/")
        ? `${parsed.pathname}${parsed.search}${parsed.hash}`
        : null
    }

    const trustedOrigins = new Set<string>()
    if (typeof window !== "undefined") trustedOrigins.add(window.location.origin)
    trustedOrigins.add(new URL(buildAgentFsDownloadUrl("__artifact_probe__"), base).origin)

    if (!trustedOrigins.has(parsed.origin)) return null
    if (!parsed.pathname.includes("/api/")) return null
    return parsed.toString()
  } catch {
    return null
  }
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null
}

function numberValue(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) ? value : null
}

function booleanValue(value: unknown) {
  return typeof value === "boolean" ? value : null
}
