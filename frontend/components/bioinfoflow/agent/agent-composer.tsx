"use client"

import { FormEvent, KeyboardEvent, useEffect, useState } from "react"
import { useTranslations } from "next-intl"

import { PermissionMenu } from "@/components/bioinfoflow/agent/permission-menu"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { Loader2, Send, Square } from "@/lib/icons"
import type {
  ActiveRunView,
  AgentPermissionMode,
  InputPart,
  AgentWorkspaceAccess,
} from "@/lib/agent/contracts"

type AgentComposerProps = {
  permissionMode: AgentPermissionMode
  workspaceAccess: AgentWorkspaceAccess
  activeRun: ActiveRunView | null
  onSendMessage: (parts: InputPart[]) => Promise<void>
  onSteer: (parts: InputPart[]) => Promise<void>
  onCancel: () => Promise<void>
  onPermissionModeChange: (mode: AgentPermissionMode) => Promise<void>
  disabled?: boolean
}

type SubmitAction = "message" | "steer"

export function AgentComposer({
  permissionMode,
  workspaceAccess,
  activeRun,
  onSendMessage,
  onSteer,
  onCancel,
  onPermissionModeChange,
  disabled = false,
}: AgentComposerProps) {
  const t = useTranslations("agentComposer")
  const [value, setValue] = useState("")
  const [submitting, setSubmitting] = useState<SubmitAction | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [stopError, setStopError] = useState<string | null>(null)
  const [cancelRequestedRunId, setCancelRequestedRunId] = useState<string | null>(null)
  const activeRunId = activeRun?.run.id ?? null
  const cancelling = Boolean(activeRunId && cancelRequestedRunId === activeRunId)
  const hasText = value.trim().length > 0
  const controlsDisabled = disabled || submitting !== null || cancelling

  useEffect(() => {
    if (!activeRunId || activeRunId !== cancelRequestedRunId) {
      setCancelRequestedRunId(null)
    }
  }, [activeRunId, cancelRequestedRunId])

  const submit = async (action: SubmitAction) => {
    const text = value.trim()
    if (!text || controlsDisabled) return
    setSubmitting(action)
    setSubmitError(null)
    try {
      const parts: InputPart[] = [{ type: "text", text }]
      if (action === "steer") await onSteer(parts)
      else await onSendMessage(parts)
      setValue("")
    } catch {
      setSubmitError(t("submitError"))
    } finally {
      setSubmitting(null)
    }
  }

  const stop = async () => {
    if (!activeRunId || cancelling || disabled) return
    setCancelRequestedRunId(activeRunId)
    setStopError(null)
    try {
      await onCancel()
    } catch {
      setCancelRequestedRunId(null)
      setStopError(t("stopError"))
    }
  }

  const handleSubmit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault()
    void submit("message")
  }

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (
      event.key !== "Enter" ||
      event.shiftKey ||
      event.nativeEvent.isComposing
    ) {
      return
    }
    event.preventDefault()
    void submit("message")
  }

  return (
    <form
      className="mx-auto flex w-full max-w-[46rem] flex-col gap-2 border-t border-border/70 bg-background px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4"
      onSubmit={handleSubmit}
    >
      <div className="rounded-xl border border-border/70 bg-background p-2 shadow-xs focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20">
        <Textarea
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
          onKeyDown={handleKeyDown}
          aria-label={t("label")}
          placeholder={t("placeholder")}
          name="agent-message"
          autoComplete="off"
          rows={2}
          disabled={disabled}
          className="max-h-40 min-h-11 resize-none border-0 bg-transparent shadow-none focus-visible:border-transparent focus-visible:ring-0"
        />

        <div className="flex min-w-0 flex-wrap items-end gap-2 pt-2">
          <PermissionMenu
            permissionMode={permissionMode}
            workspaceAccess={workspaceAccess}
            activeRun={activeRun !== null}
            onPermissionModeChange={onPermissionModeChange}
          />

          <div className="ml-auto flex items-center gap-2">
            {activeRun ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={!hasText || controlsDisabled}
                  onClick={() => void submit("steer")}
                >
                  {submitting === "steer" ? (
                    <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
                  ) : null}
                  {t(submitting === "steer" ? "steering" : "steer")}
                </Button>
                <Button
                  type="button"
                  variant="outline"
                  size="icon-sm"
                  disabled={cancelling || disabled}
                  onClick={() => void stop()}
                  aria-label={t(cancelling ? "stopping" : "stop")}
                >
                  {cancelling ? (
                    <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
                  ) : (
                    <Square aria-hidden="true" />
                  )}
                </Button>
              </>
            ) : null}
            <Button
              type="submit"
              size="icon-sm"
              disabled={!hasText || controlsDisabled}
              aria-label={t(
                submitting === "message"
                  ? "sending"
                  : activeRun
                    ? "queue"
                    : "send",
              )}
            >
              {submitting === "message" ? (
                <Loader2 aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
              ) : (
                <Send aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {submitError ? <p role="alert" className="text-sm text-destructive">{submitError}</p> : null}
      {stopError ? <p role="alert" className="text-sm text-destructive">{stopError}</p> : null}
    </form>
  )
}
