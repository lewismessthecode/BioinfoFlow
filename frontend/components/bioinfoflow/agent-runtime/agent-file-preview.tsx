"use client"

import {
  Copy,
  ExternalLink,
  Paperclip,
  X,
} from "lucide-react"
import { useTranslations } from "next-intl"

import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { buildAgentFsDownloadUrl, type AgentFsFile } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { UniversalFileRenderer } from "./universal-file-renderer"

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
  const inlineUrl = buildAgentFsDownloadUrl(file.path, { inline: true })
  const downloadUrl = buildAgentFsDownloadUrl(file.path)
  const openLabel = t("files.openDefault")
  const addLabel = t("files.addToContext")
  const copyLabel = t("files.copyPath")

  return (
    <div
      className={cn("flex min-h-0 min-w-0 flex-col overflow-hidden", className)}
      data-testid="agent-file-preview"
    >
      <div
        className="flex h-10 min-w-0 shrink-0 items-center gap-1.5 border-b border-border/60 bg-background px-2"
        data-testid="agent-file-preview-toolbar"
      >
        <button
          type="button"
          className="flex h-7 w-7 shrink-0 items-center justify-center rounded-[6px] text-muted-foreground hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
          onClick={onBack}
          aria-label={t("files.closePreview")}
        >
          <X className="h-3.5 w-3.5" />
        </button>
        <div className="min-w-0 flex-1 truncate text-sm font-medium text-foreground" title={file.path}>
          {filename}
        </div>
        <div className="flex shrink-0 items-center gap-0.5">
          <Tooltip>
            <TooltipTrigger asChild>
              <a
                href={downloadUrl}
                target="_blank"
                rel="noreferrer"
                aria-label={`${openLabel} ${filename}`}
                title={openLabel}
                className="flex h-7 w-7 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
              >
                <ExternalLink className="h-3.5 w-3.5" />
              </a>
            </TooltipTrigger>
            <TooltipContent side="bottom">{openLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
                onClick={() => onAddToContext(file.path)}
                aria-label={addLabel}
                title={addLabel}
              >
                <Paperclip className="h-3.5 w-3.5" />
              </button>
            </TooltipTrigger>
            <TooltipContent side="bottom">{addLabel}</TooltipContent>
          </Tooltip>
          <Tooltip>
            <TooltipTrigger asChild>
              <button
                type="button"
                className="flex h-7 w-7 items-center justify-center rounded-[6px] text-muted-foreground transition-colors hover:bg-muted/55 hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30"
                onClick={() => onCopyPath(file.path)}
                aria-label={copyLabel}
                title={copyLabel}
              >
                <Copy className="h-3.5 w-3.5" />
              </button>
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
