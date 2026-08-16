"use client"

import { useState } from "react"
import { useLocale, useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import { Check, Copy, Pencil, RotateCcw } from "@/lib/icons"
import {
  dateTimeAttribute,
  formatAbsoluteDateTime,
} from "@/lib/agent/date-format"
import { cn } from "@/lib/utils"

type MessageActionsProps = {
  createdAt: string
  align: "start" | "end"
  copyText?: string
  onRetry?: () => void | Promise<void>
  onEdit?: () => void
}

export function MessageActions({
  createdAt,
  align,
  copyText = "",
  onRetry,
  onEdit,
}: MessageActionsProps) {
  const locale = useLocale()
  const t = useTranslations("agentTranscript")
  const [copyState, setCopyState] = useState<"idle" | "copied" | "failed">(
    "idle",
  )
  const [actionFailed, setActionFailed] = useState(false)
  const formattedTime = formatAbsoluteDateTime(createdAt, locale)

  async function copyMessage() {
    try {
      if (!navigator.clipboard?.writeText) throw new Error("Clipboard unavailable")
      await navigator.clipboard.writeText(copyText)
      setCopyState("copied")
    } catch {
      setCopyState("failed")
    }
  }

  async function retryMessage() {
    if (!onRetry) return
    setActionFailed(false)
    try {
      await onRetry()
    } catch {
      setActionFailed(true)
    }
  }

  return (
    <>
      <footer
        className={cn(
          "mt-1.5 flex min-w-0 items-center gap-1 text-[11px] text-muted-foreground transition-opacity motion-reduce:transition-none lg:opacity-0 lg:group-hover/message:opacity-100 lg:group-focus-within/message:opacity-100",
          align === "end" ? "justify-end" : "justify-start",
        )}
      >
        {formattedTime ? (
          <time
            dateTime={dateTimeAttribute(createdAt)}
            className="px-1.5 tabular-nums"
            translate="no"
          >
            {t("timestamp", { time: formattedTime })}
          </time>
        ) : null}
        {copyText ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t(copyState === "copied" ? "copied" : "copy")}
            className="text-muted-foreground hover:text-foreground"
            onClick={() => void copyMessage()}
          >
            {copyState === "copied" ? (
              <Check data-icon="inline-start" aria-hidden="true" />
            ) : (
              <Copy data-icon="inline-start" aria-hidden="true" />
            )}
          </Button>
        ) : null}
        {onRetry ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("retry")}
            className="text-muted-foreground hover:text-foreground"
            onClick={() => void retryMessage()}
          >
            <RotateCcw data-icon="inline-start" aria-hidden="true" />
          </Button>
        ) : null}
        {onEdit ? (
          <Button
            type="button"
            variant="ghost"
            size="icon-sm"
            aria-label={t("edit")}
            className="text-muted-foreground hover:text-foreground"
            onClick={onEdit}
          >
            <Pencil data-icon="inline-start" aria-hidden="true" />
          </Button>
        ) : null}
      </footer>
      {copyState === "failed" || actionFailed ? (
        <p
          role="alert"
          aria-live="polite"
          className={cn(
            "mt-1 text-xs leading-5 text-error-foreground",
            align === "end" && "text-right",
          )}
        >
          {t(copyState === "failed" ? "copy_failed" : "action_failed")}
        </p>
      ) : null}
    </>
  )
}
