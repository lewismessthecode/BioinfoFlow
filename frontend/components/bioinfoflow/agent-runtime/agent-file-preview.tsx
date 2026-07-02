"use client"

import {
  Copy,
  Download,
  ExternalLink,
  FileText,
  Paperclip,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { buildAgentFsDownloadUrl, type AgentFsFile } from "@/lib/agent-runtime"
import { formatSize } from "@/lib/format-utils"
import { cn } from "@/lib/utils"
import { filePreviewKind } from "./file-renderer-utils"
import { fileKindLabel, UniversalFileRenderer } from "./universal-file-renderer"

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
  const kind = filePreviewKind({
    path: file.path,
    language: file.language,
    mimeType: file.mime_type,
    binary: file.binary,
  })
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
            {file.path} · {formatSize(file.size)} · {fileKindLabel(t, kind)}
          </div>
        </div>
        <div className="flex shrink-0 gap-1.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                size="sm"
                variant="outline"
                className="h-8 rounded-md bg-card px-2 transition-transform active:scale-[0.98]"
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
                className="h-8 rounded-md bg-card px-2 transition-transform active:scale-[0.98]"
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
                className="h-8 rounded-md bg-card px-2 transition-transform active:scale-[0.98]"
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
                className="h-8 rounded-md bg-card px-2 transition-transform active:scale-[0.98]"
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
      <UniversalFileRenderer
        file={{
          path: file.path,
          content: file.content,
          size: file.size,
          language: file.language,
          mimeType: file.mime_type,
          binary: file.binary,
          inlineUrl,
          downloadUrl,
        }}
      />
      {file.truncated ? (
        <p className="shrink-0 border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
          {t("files.truncated")}
        </p>
      ) : null}
    </div>
  )
}
