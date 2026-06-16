"use client"

import { X } from "lucide-react"
import { useTranslations } from "next-intl"

import type { AgentRuntimeFileRefPart } from "@/lib/agent-runtime"

export function ContextAttachments({
  attachments,
  onRemove,
}: {
  attachments: AgentRuntimeFileRefPart[]
  onRemove: (path: string) => void
}) {
  const t = useTranslations("agentRuntime")
  if (!attachments.length) return null

  return (
    <div className="flex max-w-48 flex-wrap items-center gap-1.5 sm:max-w-64" data-testid="context-attachments">
      {attachments.map((attachment) => (
        <span
          key={attachment.path}
          className="inline-flex max-w-full items-center gap-1 rounded-full border border-border/70 bg-muted/50 px-2 py-1 text-xs text-muted-foreground"
        >
          <span className="truncate">{attachment.label || attachment.path}</span>
          <button
            type="button"
            className="rounded-full hover:text-foreground"
            onClick={() => onRemove(attachment.path)}
            aria-label={t("files.removeAttachment", {
              label: attachment.label || attachment.path,
            })}
          >
            <X className="h-3 w-3" />
          </button>
        </span>
      ))}
    </div>
  )
}
