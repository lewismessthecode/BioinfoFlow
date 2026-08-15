"use client"

import type { ReactNode, Ref } from "react"
import { FormEvent, KeyboardEvent, useCallback, useEffect, useState } from "react"
import { useTranslations } from "next-intl"

import { PermissionMenu } from "@/components/bioinfoflow/agent/permission-menu"
import { AgentContextInputs } from "@/components/bioinfoflow/agent/context-inputs"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useVoiceDictation } from "@/hooks/use-voice-dictation"
import { Loader2, Mic, RotateCcw, Send, Square } from "@/lib/icons"
import type {
  ActiveRunView,
  AgentPermissionMode,
  InputPart,
  AgentWorkspaceAccess,
} from "@/lib/agent/contracts"
import type { AgentContextInput } from "@/lib/agent/context"
import { cn } from "@/lib/utils"

type AgentComposerProps = {
  permissionMode: AgentPermissionMode
  workspaceAccess: AgentWorkspaceAccess
  activeRun: ActiveRunView | null
  onSendMessage: (parts: InputPart[]) => Promise<void>
  onSteer: (parts: InputPart[]) => Promise<void>
  onCancel: () => Promise<void>
  onPermissionModeChange: (mode: AgentPermissionMode) => Promise<void>
  contextInputs?: AgentContextInput[]
  onRemoveContextInput?: (inputId: string) => void
  onContextSubmitted?: () => void
  contextControls?: ReactNode
  modelControls?: ReactNode
  placement?: "draft" | "dock"
  textareaRef?: Ref<HTMLTextAreaElement>
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
  contextInputs = [],
  onRemoveContextInput,
  onContextSubmitted,
  contextControls,
  modelControls,
  placement = "dock",
  textareaRef,
  disabled = false,
}: AgentComposerProps) {
  const t = useTranslations("agentComposer")
  const [value, setValue] = useState("")
  const [submitting, setSubmitting] = useState<SubmitAction | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [stopError, setStopError] = useState<string | null>(null)
  const [cancelRequestedRunId, setCancelRequestedRunId] = useState<string | null>(null)
  const appendTranscript = useCallback((transcript: string) => {
    const text = transcript.trim()
    if (!text) return
    setValue((current) =>
      current ? `${current}${/\s$/.test(current) ? "" : " "}${text}` : text,
    )
  }, [])
  const voice = useVoiceDictation({ onTranscript: appendTranscript })
  const activeRunId = activeRun?.run.id ?? null
  const cancelling = Boolean(activeRunId && cancelRequestedRunId === activeRunId)
  const voiceBusy =
    voice.state === "recording" || voice.state === "transcribing"
  const hasText = value.trim().length > 0
  const hasContent = hasText || contextInputs.length > 0
  const controlsDisabled =
    disabled || submitting !== null || cancelling || voiceBusy

  useEffect(() => {
    if (!activeRunId || activeRunId !== cancelRequestedRunId) {
      setCancelRequestedRunId(null)
    }
  }, [activeRunId, cancelRequestedRunId])

  const submit = async (action: SubmitAction) => {
    const text = value.trim()
    if (!hasContent || controlsDisabled) return
    setSubmitting(action)
    setSubmitError(null)
    try {
      const parts: InputPart[] = [
        ...contextInputs.map((input) => input.input_part),
        ...(text ? [{ type: "text" as const, text }] : []),
      ]
      if (action === "steer") await onSteer(parts)
      else await onSendMessage(parts)
      setValue("")
      onContextSubmitted?.()
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

  const handleVoiceAction = () => {
    if (voice.state === "recording") {
      voice.stop()
      return
    }
    if (voice.state === "error") voice.resetError()
    void voice.start()
  }

  const voiceActionLabel =
    voice.state === "recording"
      ? t("voice.stop")
      : voice.state === "transcribing"
        ? t("voice.transcribing")
        : voice.state === "error"
          ? t("voice.retry")
          : t("voice.start")

  return (
    <form
      data-testid="agent-composer"
      data-placement={placement}
      className={cn(
        "mx-auto flex w-full max-w-[46rem] flex-col gap-2 px-3 sm:px-4",
        placement === "draft"
          ? "bg-transparent pb-4"
          : "bg-gradient-to-t from-background via-background to-background/0 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))]",
      )}
      onSubmit={handleSubmit}
    >
      <div
        className={cn(
          "border border-border/65 bg-card/95 p-2 shadow-sm transition-[border-color,box-shadow] focus-within:border-ring focus-within:ring-3 focus-within:ring-ring/20 motion-reduce:transition-none",
          placement === "draft" ? "rounded-[22px] p-3 shadow-md" : "rounded-2xl",
        )}
      >
        {contextInputs.length > 0 && onRemoveContextInput ? (
          <div className="px-1 pt-1 pb-2">
            <AgentContextInputs
              inputs={contextInputs}
              onRemove={onRemoveContextInput}
              disabled={controlsDisabled}
            />
          </div>
        ) : null}
        <Textarea
          ref={textareaRef}
          value={value}
          onChange={(event) => setValue(event.currentTarget.value)}
          onKeyDown={handleKeyDown}
          aria-label={t("label")}
          placeholder={t("placeholder")}
          name="agent-message"
          autoComplete="off"
          rows={placement === "draft" ? 3 : 2}
          disabled={disabled}
          className={cn(
            "max-h-40 resize-none border-0 bg-transparent shadow-none focus-visible:border-transparent focus-visible:ring-0",
            placement === "draft" ? "min-h-20 text-[15px]" : "min-h-11",
          )}
        />

        <div className="flex min-w-0 flex-wrap items-end gap-2 pt-2">
          {contextControls}
          {modelControls}
          <PermissionMenu
            permissionMode={permissionMode}
            workspaceAccess={workspaceAccess}
            activeRun={activeRun !== null}
            disabled={disabled}
            onPermissionModeChange={onPermissionModeChange}
          />

          <div className="ml-auto flex items-center gap-2">
            {voice.available ? (
              <>
                {voice.state === "recording" ? (
                  <span role="status" className="text-xs text-muted-foreground">
                    {t("voice.recording", {
                      seconds: voice.elapsedSeconds,
                    })}
                  </span>
                ) : voice.state === "transcribing" ? (
                  <span role="status" className="text-xs text-muted-foreground">
                    {t("voice.transcribing")}
                  </span>
                ) : null}
                <Button
                  type="button"
                  variant="ghost"
                  size="icon-sm"
                  disabled={
                    voice.state === "transcribing" ||
                    (voice.state !== "recording" &&
                      (disabled || submitting !== null || cancelling))
                  }
                  onClick={handleVoiceAction}
                  aria-label={voiceActionLabel}
                  aria-pressed={voice.state === "recording"}
                >
                  {voice.state === "transcribing" ? (
                    <Loader2
                      data-icon="inline-start"
                      aria-hidden="true"
                      className="animate-spin motion-reduce:animate-none"
                    />
                  ) : voice.state === "recording" ? (
                    <Square data-icon="inline-start" aria-hidden="true" />
                  ) : voice.state === "error" ? (
                    <RotateCcw data-icon="inline-start" aria-hidden="true" />
                  ) : (
                    <Mic data-icon="inline-start" aria-hidden="true" />
                  )}
                </Button>
              </>
            ) : null}
            {activeRun ? (
              <>
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  disabled={!hasContent || controlsDisabled}
                  onClick={() => void submit("steer")}
                >
                  {submitting === "steer" ? (
                    <Loader2
                      data-icon="inline-start"
                      aria-hidden="true"
                      className="animate-spin motion-reduce:animate-none"
                    />
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
                    <Loader2
                      data-icon="inline-start"
                      aria-hidden="true"
                      className="animate-spin motion-reduce:animate-none"
                    />
                  ) : (
                    <Square data-icon="inline-start" aria-hidden="true" />
                  )}
                </Button>
              </>
            ) : null}
            <Button
              type="submit"
              size="icon-sm"
              disabled={!hasContent || controlsDisabled}
              aria-label={t(
                submitting === "message"
                  ? "sending"
                  : activeRun
                    ? "queue"
                    : "send",
              )}
            >
              {submitting === "message" ? (
                <Loader2
                  data-icon="inline-start"
                  aria-hidden="true"
                  className="animate-spin motion-reduce:animate-none"
                />
              ) : (
                <Send data-icon="inline-start" aria-hidden="true" />
              )}
            </Button>
          </div>
        </div>
      </div>

      {submitError ? <p role="alert" className="text-sm text-destructive">{submitError}</p> : null}
      {stopError ? <p role="alert" className="text-sm text-destructive">{stopError}</p> : null}
      {voice.state === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("voice.error")}
        </p>
      ) : null}
    </form>
  )
}
