"use client"

import { Copy, FileText, Paperclip, X } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentFsFile } from "@/lib/agent-runtime"
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
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card px-2"
            onClick={() => onAddToContext(file.path)}
          >
            <Paperclip className="h-3.5 w-3.5" />
            <span className="hidden xl:inline">{t("files.addToContext")}</span>
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card px-2"
            onClick={() => onCopyPath(file.path)}
          >
            <Copy className="h-3.5 w-3.5" />
            <span className="hidden xl:inline">{t("files.copyPath")}</span>
          </Button>
        </div>
      </div>
      <pre className="min-h-0 min-w-0 flex-1 overflow-auto bg-muted/20 p-3 text-xs leading-5 text-foreground">
        <code>{file.content || "—"}</code>
      </pre>
      {file.truncated ? (
        <p className="shrink-0 border-t border-border/60 px-3 py-2 text-xs text-muted-foreground">
          {t("files.truncated")}
        </p>
      ) : null}
    </div>
  )
}
