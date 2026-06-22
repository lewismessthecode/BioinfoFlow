"use client"

import { useCallback, useState } from "react"
import {
  Box,
  Copy,
  Download,
  FileJson,
  FileCode,
  FileSpreadsheet,
  FileText,
  ListChecks,
  Play,
  TerminalSquare,
  Workflow,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import type { AgentRuntimeArtifact, AgentTodoItem } from "@/lib/agent-runtime"
import { TodoChecklist } from "./todo-checklist"

export function ArtifactViewer({ artifact }: { artifact: AgentRuntimeArtifact }) {
  switch (artifact.type) {
    case "file":
    case "html":
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
    case "image":
      return <RecordArtifact artifact={artifact} recordKey="image" />
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
  const kind = artifactFileKind(artifact, path, payload)
  const table = kind === "spreadsheet" ? tableFromArtifact(payload, content, path) : null
  const resourceUrl = artifactResourceUrl(artifact)
  const canCopyOrDownload = content.length > 0
  return (
    <div className="grid gap-3">
      <ArtifactHeader title={path} />
      {canCopyOrDownload ? (
        <div className="flex items-center gap-2">
          <CopyButton text={content} label={t("artifacts.copy")} done={t("artifacts.copied")} />
          <DownloadButton
            text={content}
            filename={filename}
            label={t("artifacts.download")}
          />
        </div>
      ) : null}
      {kind === "markdown" ? (
        <MarkdownRenderer
          content={content || t("artifacts.previewUnavailable")}
          className="rounded-2xl border border-border/70 bg-background px-4 py-3 text-sm"
        />
      ) : kind === "html" && (content || resourceUrl) ? (
        <iframe
          title={filename}
          src={resourceUrl || undefined}
          srcDoc={resourceUrl ? undefined : content}
          sandbox=""
          className="h-[60vh] w-full rounded-2xl border border-border/70 bg-background"
        />
      ) : kind === "pdf" && resourceUrl ? (
        <iframe
          title={filename}
          src={resourceUrl}
          className="h-[60vh] w-full rounded-2xl border border-border/70 bg-background"
        />
      ) : table ? (
        <ArtifactTable rows={table} />
      ) : (
        <pre className="max-h-[60vh] overflow-auto rounded-2xl border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
          <code>{content || t("artifacts.previewUnavailable")}</code>
        </pre>
      )}
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

function ArtifactTable({ rows }: { rows: string[][] }) {
  const [header, ...body] = rows
  return (
    <div className="max-h-[60vh] overflow-auto rounded-2xl border border-border/70 bg-background">
      <table className="w-full border-collapse text-left text-sm">
        <thead className="sticky top-0 bg-muted/80 text-xs font-medium text-muted-foreground">
          <tr>
            {header.map((cell, index) => (
              <th key={`${cell}-${index}`} className="border-b border-border/70 px-3 py-2">
                {cell || "—"}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row, rowIndex) => (
            <tr key={rowIndex} className="border-b border-border/50 last:border-b-0">
              {header.map((_, cellIndex) => (
                <td key={cellIndex} className="px-3 py-2 align-top text-foreground">
                  {row[cellIndex] || ""}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
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
    <Button type="button" size="sm" variant="outline" className="h-8 rounded-full bg-card" onClick={onCopy}>
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
    <Button type="button" size="sm" variant="outline" className="h-8 rounded-full bg-card" onClick={onDownload}>
      <Download className="h-3.5 w-3.5" />
      {label}
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
  const known = ["file", "command", "html", "markdown", "pdf", "run", "sheet", "spreadsheet", "workflow", "image"]
  if (known.includes(type)) return t(`artifacts.types.${type}`)
  if (type === "log_summary") return t("artifacts.types.command")
  if (type === "todo_list") return t("artifacts.types.todo_list")
  return t("artifacts.types.unknown")
}

function artifactFileKind(
  artifact: AgentRuntimeArtifact,
  path: string,
  payload: Record<string, unknown>,
) {
  const type = artifact.type.toLowerCase()
  const mimeType = stringValue(payload.mime_type)?.toLowerCase() ?? ""
  const lowerPath = path.toLowerCase()
  if (type === "html" || mimeType.includes("html") || lowerPath.endsWith(".html") || lowerPath.endsWith(".htm")) {
    return "html"
  }
  if (type === "pdf" || mimeType.includes("pdf") || lowerPath.endsWith(".pdf")) {
    return "pdf"
  }
  if (
    type === "sheet" ||
    type === "spreadsheet" ||
    mimeType.includes("csv") ||
    mimeType.includes("tab-separated") ||
    lowerPath.endsWith(".csv") ||
    lowerPath.endsWith(".tsv")
  ) {
    return "spreadsheet"
  }
  if (
    type === "markdown" ||
    lowerPath.endsWith(".md") ||
    lowerPath.endsWith(".markdown") ||
    mimeType.includes("markdown")
  ) {
    return "markdown"
  }
  return "text"
}

function artifactResourceUrl(artifact: AgentRuntimeArtifact) {
  const payload = artifact.payload ?? {}
  const payloadUrl = stringValue(payload.url) ?? stringValue(payload.href)
  if (payloadUrl) return payloadUrl
  const resource = artifact.resource_ref
  if (!resource || typeof resource !== "object") return null
  return stringValue(resource.url) ?? stringValue(resource.href)
}

function tableFromArtifact(
  payload: Record<string, unknown>,
  content: string,
  path: string,
) {
  if (Array.isArray(payload.rows)) {
    const rows = payload.rows
      .filter(Array.isArray)
      .map((row) => row.map((cell) => String(cell ?? "")))
    return rows.length ? rows : null
  }
  if (!content.trim()) return null
  const delimiter = path.toLowerCase().endsWith(".tsv") ? "\t" : ","
  const rows = parseDelimitedRows(content, delimiter)
  return rows.length ? rows : null
}

function parseDelimitedRows(content: string, delimiter: "," | "\t") {
  return content
    .trim()
    .split(/\r?\n/)
    .slice(0, 200)
    .map((line) => parseDelimitedLine(line, delimiter))
    .filter((row) => row.some((cell) => cell.trim().length > 0))
}

function parseDelimitedLine(line: string, delimiter: "," | "\t") {
  const cells: string[] = []
  let current = ""
  let quoted = false
  for (let index = 0; index < line.length; index += 1) {
    const char = line[index]
    if (char === '"') {
      if (quoted && line[index + 1] === '"') {
        current += '"'
        index += 1
      } else {
        quoted = !quoted
      }
      continue
    }
    if (char === delimiter && !quoted) {
      cells.push(current)
      current = ""
      continue
    }
    current += char
  }
  cells.push(current)
  return cells
}

function stringValue(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null
}
