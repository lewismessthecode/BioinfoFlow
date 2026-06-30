"use client"

import {
  Copy,
  Download,
  ExternalLink,
  FileCode,
  FileText,
  Paperclip,
  Table,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { MarkdownRenderer } from "@/components/bioinfoflow/markdown-renderer"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { buildAgentFsDownloadUrl, type AgentFsFile } from "@/lib/agent-runtime"
import { formatSize } from "@/lib/format-utils"
import { cn } from "@/lib/utils"

export function AgentFilePreview({
  file,
  className,
  onBack,
  onAddToContext,
  onCopyPath,
}: {
  file: AgentFsFile
  className?: string
  onBack: () => void
  onAddToContext: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")
  const filename = file.path.split("/").pop() || file.path
  const kind = filePreviewKind(file)
  const inlineUrl = buildAgentFsDownloadUrl(file.path, { inline: true })
  const downloadUrl = buildAgentFsDownloadUrl(file.path)
  const openLabel = t("files.openDefault")
  const downloadLabel = t("files.download")
  const addLabel = t("files.addToContext")
  const copyLabel = t("files.copyPath")

  return (
    <div
      className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden", className)}
      data-testid="agent-file-preview"
    >
      <div className="flex min-w-0 shrink-0 items-center gap-2 border-b border-border/60 bg-background px-3 py-2">
        <button
          type="button"
          className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-muted-foreground hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
          onClick={onBack}
          aria-label={t("files.closePreview")}
        >
          <X className="h-4 w-4" />
        </button>
        <FileText className="h-4 w-4 shrink-0 text-muted-foreground" />
        <div className="min-w-0 flex-1" title={file.path}>
          <div className="truncate text-sm font-medium text-foreground">{filename}</div>
          <div className="truncate font-mono text-[11px] text-muted-foreground">
            {file.path} · {formatSize(file.size)} · {file.language || "text"}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-lg bg-card px-2"
                asChild
              >
                <a
                  href={downloadUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={openLabel}
                  title={openLabel}
                >
                  <ExternalLink className="h-3.5 w-3.5" />
                  <span className="hidden 2xl:inline">{openLabel}</span>
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{openLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-lg bg-card px-2"
                asChild
              >
                <a href={downloadUrl} aria-label={downloadLabel} title={downloadLabel}>
                  <Download className="h-3.5 w-3.5" />
                  <span className="hidden 2xl:inline">{downloadLabel}</span>
                </a>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{downloadLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 rounded-lg bg-card px-2"
                onClick={() => onAddToContext(file.path)}
                aria-label={addLabel}
                title={addLabel}
              >
                <Paperclip className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{addLabel}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{addLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                type="button"
                size="sm"
                variant="outline"
                className="h-8 rounded-lg bg-card px-2"
                onClick={() => onCopyPath(file.path)}
                aria-label={copyLabel}
                title={copyLabel}
              >
                <Copy className="h-3.5 w-3.5" />
                <span className="hidden xl:inline">{copyLabel}</span>
              </Button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{copyLabel}</TooltipContent>
          </Tooltip>
        </div>
      </div>
      <FilePreviewBody file={file} kind={kind} inlineUrl={inlineUrl} />
      {file.truncated ? (
        <p className="shrink-0 border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
          {t("files.truncated")}
        </p>
      ) : null}
    </div>
  )
}

function FilePreviewBody({
  file,
  kind,
  inlineUrl,
}: {
  file: AgentFsFile
  kind: FilePreviewKind
  inlineUrl: string
}) {
  const t = useTranslations("agentRuntime")

  if (kind === "markdown") {
    return (
      <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-background p-3">
        <MarkdownRenderer
          content={file.content || t("files.previewUnavailable")}
          className="rounded-lg border border-border/65 bg-card px-4 py-3 text-sm"
        />
      </div>
    )
  }

  if (kind === "html") {
    return (
      <iframe
        title={file.path}
        srcDoc={file.content || undefined}
        src={file.content ? undefined : inlineUrl}
        sandbox=""
        className="min-h-0 min-w-0 flex-1 border-0 bg-background"
      />
    )
  }

  if (kind === "pdf") {
    return (
      <iframe
        title={file.path}
        src={inlineUrl}
        className="min-h-0 min-w-0 flex-1 border-0 bg-background"
      />
    )
  }

  if (kind === "table") {
    const rows = parseDelimitedRows(
      file.content,
      file.path.toLowerCase().endsWith(".tsv") ? "\t" : ",",
    )
    if (rows.length > 0) return <DelimitedTable rows={rows} />
  }

  if (kind === "unsupported") {
    return (
      <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center bg-muted/20 p-6 text-center">
        <div className="max-w-sm">
          <FileCode className="mx-auto h-8 w-8 text-muted-foreground" />
          <p className="mt-3 text-sm font-medium text-foreground">
            {t("files.previewUnsupported")}
          </p>
          <p className="mt-1.5 text-xs leading-5 text-muted-foreground">
            {t("files.openDefaultDescription")}
          </p>
        </div>
      </div>
    )
  }

  return (
    <pre className="min-h-0 min-w-0 flex-1 overflow-auto bg-muted/20 p-3 text-xs leading-5 text-foreground">
      <code>{file.content || t("files.previewUnavailable")}</code>
    </pre>
  )
}

function DelimitedTable({ rows }: { rows: string[][] }) {
  const [header, ...body] = rows
  return (
    <div className="min-h-0 min-w-0 flex-1 overflow-auto bg-background p-3">
      <div className="overflow-auto rounded-lg border border-border/65 bg-card">
        <table className="w-full border-collapse text-left text-sm">
          <thead className="sticky top-0 bg-muted/85 text-xs font-medium text-muted-foreground">
            <tr>
              {header.map((cell, index) => (
                <th key={`${cell}-${index}`} className="border-b border-border/65 px-3 py-2">
                  <span className="inline-flex items-center gap-1.5">
                    {index === 0 ? <Table className="h-3.5 w-3.5" /> : null}
                    {cell || "—"}
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, rowIndex) => (
              <tr key={rowIndex} className="border-b border-border/45 last:border-b-0">
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
    </div>
  )
}

type FilePreviewKind = "markdown" | "html" | "pdf" | "table" | "text" | "unsupported"

function filePreviewKind(file: AgentFsFile): FilePreviewKind {
  const lowerPath = file.path.toLowerCase()
  const language = file.language?.toLowerCase() ?? ""
  const mime = file.mime_type?.toLowerCase() ?? ""
  if (language === "markdown" || lowerPath.endsWith(".md") || lowerPath.endsWith(".markdown")) {
    return "markdown"
  }
  if (language === "html" || mime.includes("html") || lowerPath.endsWith(".html") || lowerPath.endsWith(".htm")) {
    return "html"
  }
  if (language === "pdf" || mime.includes("pdf") || lowerPath.endsWith(".pdf")) {
    return "pdf"
  }
  if (
    language === "csv" ||
    language === "tsv" ||
    mime.includes("csv") ||
    mime.includes("tab-separated") ||
    lowerPath.endsWith(".csv") ||
    lowerPath.endsWith(".tsv")
  ) {
    return "table"
  }
  if (file.binary || lowerPath.endsWith(".xlsx") || lowerPath.endsWith(".xls")) {
    return "unsupported"
  }
  return "text"
}

function parseDelimitedRows(content: string, delimiter: "," | "\t") {
  if (!content.trim()) return []
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
