"use client"

import type { RefObject } from "react"
import { Trash2 } from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import type { AgentComposerAttachment } from "./attachment-strip"

type AttachmentPreviewDialogProps = {
  open: boolean
  attachment: AgentComposerAttachment | null
  onOpenChange: (open: boolean) => void
  onDelete?: (attachment: AgentComposerAttachment) => void
  readOnly?: boolean
  returnFocusRef?: RefObject<HTMLElement | null>
}

export function AttachmentPreviewDialog({
  open,
  attachment,
  onOpenChange,
  onDelete,
  readOnly = false,
  returnFocusRef,
}: AttachmentPreviewDialogProps) {
  const t = useTranslations("agentRuntime.attachments")
  if (!attachment) return null
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-h-[calc(100dvh-2rem)] max-w-[min(72rem,calc(100vw-2rem))] gap-3 overflow-hidden rounded-xl border-border bg-background p-3 shadow-[0_18px_60px_rgba(15,23,42,0.14)]"
        onCloseAutoFocus={(event) => {
          if (!returnFocusRef?.current) return
          event.preventDefault()
          returnFocusRef.current.focus()
        }}
      >
        <DialogHeader className="min-w-0 pr-10">
          <DialogTitle className="truncate text-sm">{attachment.filename}</DialogTitle>
          <DialogDescription className="sr-only">
            {t("imagePreview")}
          </DialogDescription>
        </DialogHeader>
        <div className="flex min-h-0 items-center justify-center overflow-auto rounded-lg bg-muted/40 p-2">
          {/* eslint-disable-next-line @next/next/no-img-element -- private authenticated preview URL */}
          <img
            src={attachment.previewUrl || ""}
            alt={attachment.filename}
            className="max-h-[calc(100dvh-9rem)] max-w-full object-contain"
          />
        </div>
        {!readOnly && onDelete ? (
          <div className="flex justify-end">
            <Button
              type="button"
              variant="ghost"
              size="sm"
              className="text-destructive hover:bg-destructive/10 hover:text-destructive"
              onClick={() => onDelete(attachment)}
              aria-label={t("delete", { name: attachment.filename })}
            >
              <Trash2 className="h-4 w-4" />
              {t("deleteAction")}
            </Button>
          </div>
        ) : null}
      </DialogContent>
    </Dialog>
  )
}
