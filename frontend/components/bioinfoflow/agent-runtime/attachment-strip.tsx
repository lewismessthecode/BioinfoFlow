"use client"

import { AlertCircle, File, Folder, Image as ImageIcon, Loader2, RotateCcw, X } from "@/lib/icons"
import { cn } from "@/lib/utils"
import { useTranslations } from "next-intl"

export type AgentComposerAttachment = {
  id: string
  filename: string
  kind: "file" | "folder" | "image"
  status: "uploading" | "ready" | "error" | "deleting"
  previewUrl?: string | null
  error?: string | null
}

type AttachmentStripProps = {
  attachments: AgentComposerAttachment[]
  onPreview?: (attachment: AgentComposerAttachment) => void
  onRemove: (attachment: AgentComposerAttachment) => void
  onRetry?: (attachment: AgentComposerAttachment) => void
  readOnly?: boolean
}

export function AttachmentStrip({
  attachments,
  onPreview,
  onRemove,
  onRetry,
  readOnly = false,
}: AttachmentStripProps) {
  const t = useTranslations("agentRuntime.attachments")
  if (!attachments.length) return null
  return (
    <div className="flex min-w-0 gap-2 overflow-x-auto px-2 pt-1" aria-label={t("label")}>
      {attachments.map((attachment) => {
        const canPreview =
          attachment.kind === "image" &&
          attachment.status === "ready" &&
          Boolean(attachment.previewUrl && onPreview)
        return (
          <div
            key={attachment.id}
            className={cn(
              "relative flex h-14 min-w-[10rem] max-w-[14rem] items-center gap-2 rounded-lg border border-border bg-muted/35 px-2.5",
              attachment.status === "error" && "border-destructive/30 bg-destructive/5",
            )}
          >
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-2 text-left disabled:cursor-default"
              onClick={() => canPreview && onPreview?.(attachment)}
              disabled={!canPreview}
              aria-label={canPreview ? t("preview", { name: attachment.filename }) : undefined}
            >
              <AttachmentIcon attachment={attachment} />
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-medium text-foreground">
                  {attachment.filename}
                </span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {attachment.status === "uploading"
                    ? t("uploading")
                    : attachment.status === "deleting"
                      ? t("removing")
                      : attachment.status === "error"
                        ? attachment.error || t("uploadFailed")
                        : attachment.kind}
                </span>
              </span>
            </button>
            {!readOnly && attachment.status === "error" && onRetry ? (
              <button
                type="button"
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground"
                onClick={() => onRetry(attachment)}
                aria-label={t("retry", { name: attachment.filename })}
              >
                <RotateCcw className="h-3.5 w-3.5" />
              </button>
            ) : null}
            {!readOnly ? (
              <button
                type="button"
                className="rounded-md p-1 text-muted-foreground hover:bg-accent hover:text-foreground disabled:opacity-50"
                onClick={() => onRemove(attachment)}
                disabled={attachment.status === "deleting"}
                aria-label={t("remove", { name: attachment.filename })}
              >
                <X className="h-3.5 w-3.5" />
              </button>
            ) : null}
          </div>
        )
      })}
    </div>
  )
}

function AttachmentIcon({ attachment }: { attachment: AgentComposerAttachment }) {
  if (attachment.status === "uploading" || attachment.status === "deleting") {
    return <Loader2 className="h-5 w-5 shrink-0 animate-spin text-muted-foreground motion-reduce:animate-none" />
  }
  if (attachment.status === "error") {
    return <AlertCircle className="h-5 w-5 shrink-0 text-destructive" />
  }
  if (attachment.kind === "image" && attachment.previewUrl) {
    return (
      // eslint-disable-next-line @next/next/no-img-element -- private authenticated preview URL
      <img
        src={attachment.previewUrl}
        alt={attachment.filename}
        className="h-9 w-9 shrink-0 rounded-md border border-border object-cover"
      />
    )
  }
  const Icon = attachment.kind === "folder" ? Folder : attachment.kind === "image" ? ImageIcon : File
  return <Icon className="h-5 w-5 shrink-0 text-muted-foreground" />
}
