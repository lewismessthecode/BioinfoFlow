"use client"

import { ChevronLeft, Copy, Paperclip } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentFsFile } from "@/lib/agent-runtime"

export function AgentFilePreview({
  file,
  onBack,
  onAddToContext,
  onCopyPath,
}: {
  file: AgentFsFile
  onBack: () => void
  onAddToContext: (path: string) => void
  onCopyPath: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")

  return (
    <div className="grid gap-3" data-testid="agent-file-preview">
      <button
        type="button"
        className="flex w-fit items-center gap-1.5 text-sm font-medium text-foreground"
        onClick={onBack}
      >
        <ChevronLeft className="h-4 w-4" />
        {t("files.back")}
      </button>
      <div className="grid gap-2 rounded-2xl border border-border/70 bg-card p-3">
        <div className="break-words font-mono text-xs text-muted-foreground">{file.path}</div>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card"
            onClick={() => onAddToContext(file.path)}
          >
            <Paperclip className="h-3.5 w-3.5" />
            {t("files.addToContext")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card"
            onClick={() => onCopyPath(file.path)}
          >
            <Copy className="h-3.5 w-3.5" />
            {t("files.copyPath")}
          </Button>
        </div>
      </div>
      <pre className="max-h-[54vh] overflow-auto rounded-2xl border border-border/70 bg-muted/30 p-3 text-xs leading-5 text-foreground">
        <code>{file.content || "—"}</code>
      </pre>
      {file.truncated ? (
        <p className="text-xs text-muted-foreground">{t("files.truncated")}</p>
      ) : null}
    </div>
  )
}
