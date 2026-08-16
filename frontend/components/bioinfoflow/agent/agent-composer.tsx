"use client"

import type { ReactNode, Ref } from "react"
import {
  FormEvent,
  KeyboardEvent,
  useCallback,
  useEffect,
  useLayoutEffect,
  useRef,
  useState,
} from "react"
import { useTranslations } from "next-intl"

import { PermissionMenu } from "@/components/bioinfoflow/agent/permission-menu"
import {
  EnvironmentSelector,
  type AgentEnvironmentSelection,
  type AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import { AgentContextInputs } from "@/components/bioinfoflow/agent/context-inputs"
import { Button } from "@/components/ui/button"
import { Textarea } from "@/components/ui/textarea"
import { useVoiceDictation } from "@/hooks/use-voice-dictation"
import {
  ArrowUpRight,
  CircleCheck,
  Loader2,
  MessageCircle,
  Mic,
  RotateCcw,
  Send,
  Square,
} from "@/lib/icons"
import type {
  ActiveWork,
  ComposerInputPart,
  ConversationPermissionMode,
  ConversationWorkspaceAccess,
} from "@/lib/agent/conversation-model/types"
import type { AgentContextInput } from "@/lib/agent/context"
import { cn } from "@/lib/utils"

type AgentComposerProps = {
  permissionMode: ConversationPermissionMode
  workspaceAccess: ConversationWorkspaceAccess
  activeRun: ActiveWork | null
  onSendMessage: (parts: ComposerInputPart[]) => Promise<void>
  onSteer: (parts: ComposerInputPart[]) => Promise<void>
  onCancel: () => Promise<void>
  onPermissionModeChange: (mode: ConversationPermissionMode) => Promise<void>
  contextInputs?: AgentContextInput[]
  onRemoveContextInput?: (inputId: string) => void
  onContextSubmitted?: () => void
  contextControls?: ReactNode
  modelControls?: ReactNode
  environmentTargets?: readonly AgentEnvironmentTarget[]
  environmentSelection?: AgentEnvironmentSelection
  effectiveEnvironmentSelection?: AgentEnvironmentSelection
  environmentSelectionPending?: boolean
  onEnvironmentSelectionChange?: (
    selection: AgentEnvironmentSelection,
  ) => Promise<void>
  starterPrompts?: readonly string[]
  placement?: "draft" | "dock"
  textareaRef?: Ref<HTMLTextAreaElement>
  disabled?: boolean
  renderCommandDiscoveryHint?: boolean
  onDraftEmptyChange?: (empty: boolean) => void
}

type SubmitAction = "message" | "steer"

const starterSlotIcons = [
  { name: "circle-check", icon: CircleCheck },
  { name: "message-circle", icon: MessageCircle },
  { name: "rotate-ccw", icon: RotateCcw },
] as const

const commandHints = [
  { key: "skills", token: "/" },
  { key: "context", token: "@" },
] as const

export function AgentCommandDiscoveryHint({
  visible,
}: {
  visible: boolean
}) {
  const t = useTranslations("agentComposer")
  const [commandHintIndex, setCommandHintIndex] = useState(0)
  const [commandHintSwapState, setCommandHintSwapState] = useState<
    "" | "is-exit" | "is-enter-start"
  >("")

  useEffect(() => {
    if (
      !visible ||
      globalThis.matchMedia?.("(prefers-reduced-motion: reduce)").matches
    ) {
      return
    }

    const timers = new Set<ReturnType<typeof setTimeout>>()
    const addTimer = (callback: () => void, delay: number) => {
      const timer = setTimeout(() => {
        timers.delete(timer)
        callback()
      }, delay)
      timers.add(timer)
    }
    const interval = setInterval(() => {
      setCommandHintSwapState("is-exit")
      addTimer(() => {
        setCommandHintIndex((index) => (index + 1) % commandHints.length)
        setCommandHintSwapState("is-enter-start")
        addTimer(() => setCommandHintSwapState(""), 16)
      }, 150)
    }, 5200)

    return () => {
      clearInterval(interval)
      timers.forEach((timer) => clearTimeout(timer))
    }
  }, [visible])

  if (!visible) return null
  const hint = commandHints[commandHintIndex] ?? commandHints[0]

  return (
    <div
      data-testid="agent-command-discovery-hint"
      className="agent-center-stage pointer-events-none absolute inset-x-14 bottom-24 flex justify-center sm:inset-x-4 sm:bottom-12"
    >
      <p
        className={cn(
          "t-text-swap inline-flex max-w-[calc(100vw-2rem)] items-center justify-center gap-1.5 truncate text-center text-[12px] font-normal leading-5 tracking-normal text-muted-foreground/75 sm:text-[13px]",
          commandHintSwapState,
        )}
        aria-label={`${t(`commandHints.${hint.key}.prefix`)} ${hint.token} ${t(`commandHints.${hint.key}.suffix`)}`}
      >
        <span className="truncate">{t(`commandHints.${hint.key}.prefix`)}</span>
        <kbd className="rounded-[5px] border border-border/35 bg-foreground/[0.055] px-1.5 py-px font-mono text-[11px] font-normal leading-none text-muted-foreground/85">
          {hint.token}
        </kbd>
        <span className="truncate">{t(`commandHints.${hint.key}.suffix`)}</span>
      </p>
    </div>
  )
}

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
  environmentTargets = [],
  environmentSelection = { mode: "auto" },
  effectiveEnvironmentSelection,
  environmentSelectionPending = false,
  onEnvironmentSelectionChange,
  starterPrompts = [],
  placement = "dock",
  textareaRef,
  disabled = false,
  renderCommandDiscoveryHint = true,
  onDraftEmptyChange,
}: AgentComposerProps) {
  const t = useTranslations("agentComposer")
  const [value, setValue] = useState("")
  const [submitting, setSubmitting] = useState<SubmitAction | null>(null)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [stopError, setStopError] = useState<string | null>(null)
  const [cancelRequestedRunId, setCancelRequestedRunId] = useState<
    string | null
  >(null)
  const localTextareaRef = useRef<HTMLTextAreaElement | null>(null)
  const appendTranscript = useCallback((transcript: string) => {
    const text = transcript.trim()
    if (!text) return
    setValue((current) =>
      current ? `${current}${/\s$/.test(current) ? "" : " "}${text}` : text,
    )
  }, [])
  const voice = useVoiceDictation({ onTranscript: appendTranscript })
  const activeRunId = activeRun?.runId ?? null
  const cancelling = Boolean(
    activeRunId && cancelRequestedRunId === activeRunId,
  )
  const voiceBusy =
    voice.state === "recording" || voice.state === "transcribing"
  const hasText = value.trim().length > 0
  const hasContent = hasText || contextInputs.length > 0
  const controlsDisabled =
    disabled || submitting !== null || cancelling || voiceBusy

  const setTextareaNode = useCallback(
    (node: HTMLTextAreaElement | null) => {
      localTextareaRef.current = node
      if (typeof textareaRef === "function") textareaRef(node)
      else if (textareaRef) textareaRef.current = node
    },
    [textareaRef],
  )

  const resizeTextarea = useCallback(
    (node: HTMLTextAreaElement) => {
      const minimumHeight = placement === "draft" ? 80 : 44
      node.style.height = "auto"
      const contentHeight = node.scrollHeight || minimumHeight
      node.style.height = `${Math.min(Math.max(contentHeight, minimumHeight), 160)}px`
      node.style.overflowY = contentHeight > 160 ? "auto" : "hidden"
    },
    [placement],
  )

  useLayoutEffect(() => {
    if (localTextareaRef.current) resizeTextarea(localTextareaRef.current)
  }, [resizeTextarea, value])

  useEffect(() => {
    if (!activeRunId || activeRunId !== cancelRequestedRunId) {
      setCancelRequestedRunId(null)
    }
  }, [activeRunId, cancelRequestedRunId])

  useEffect(() => {
    if (placement === "draft") onDraftEmptyChange?.(!value.trim())
  }, [onDraftEmptyChange, placement, value])

  const submit = async (action: SubmitAction) => {
    const text = value.trim()
    if (!hasContent || controlsDisabled) return
    setSubmitting(action)
    setSubmitError(null)
    try {
      const parts: ComposerInputPart[] = [
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
        "mx-auto flex w-full flex-col gap-2",
        placement === "draft"
          ? "max-w-[42rem] bg-transparent px-0 pb-4"
          : "max-w-[48rem] bg-background px-3 pt-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] sm:px-4",
      )}
      onSubmit={handleSubmit}
    >
      <div
        data-testid={
          placement === "draft" ? "agent-composer-draft-shell" : undefined
        }
        className={placement === "draft" ? "relative" : "contents"}
      >
        <div
          data-testid="agent-composer-surface"
          className={cn(
            "flex flex-col border border-border bg-card p-2 transition-[border-color,box-shadow,background-color] focus-within:border-foreground/25 focus-within:shadow-[0_12px_28px_-24px_color-mix(in_oklab,var(--foreground)_22%,transparent)] motion-reduce:transition-none",
            placement === "draft"
              ? "rounded-[24px] shadow-[0_1px_2px_rgba(15,15,15,0.035)]"
              : "rounded-[18px] shadow-[0_12px_34px_-28px_color-mix(in_oklab,var(--foreground)_24%,transparent)]",
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
            ref={setTextareaNode}
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
              "max-h-40 resize-none border-0 bg-transparent shadow-none dark:bg-transparent focus-visible:border-transparent focus-visible:ring-0",
              placement === "draft"
                ? "min-h-20 flex-1 text-[15px]"
                : "min-h-11",
            )}
          />

          <div
            data-testid="agent-composer-controls"
            className={cn(
              "flex min-w-0 flex-wrap gap-2 pt-2",
              placement === "draft" ? "mt-auto items-center" : "items-end",
            )}
          >
            {contextControls}
            {modelControls}
            <PermissionMenu
              permissionMode={permissionMode}
              workspaceAccess={workspaceAccess}
              disabled={disabled}
              onPermissionModeChange={onPermissionModeChange}
            />
            {onEnvironmentSelectionChange ? (
              <EnvironmentSelector
                targets={environmentTargets}
                requested={environmentSelection}
                effective={effectiveEnvironmentSelection}
                pending={environmentSelectionPending}
                disabled={disabled}
                onChange={onEnvironmentSelectionChange}
              />
            ) : null}

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
                  size="icon-sm"
                  disabled={!hasContent || controlsDisabled}
                  onClick={() => void submit("steer")}
                  aria-label={t(
                    submitting === "steer" ? "steering" : "steer",
                  )}
                  data-agent-action="steer"
                >
                  {submitting === "steer" ? (
                    <Loader2
                      data-icon="inline-start"
                      aria-hidden="true"
                      className="animate-spin motion-reduce:animate-none"
                    />
                  ) : (
                    <ArrowUpRight aria-hidden="true" />
                  )}
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

        {placement === "draft" && starterPrompts.length > 0 ? (
          <section
            data-testid="agent-starter-prompt-list"
            className="absolute inset-x-0 top-full mt-5 w-full overflow-hidden"
            aria-label={t("starterHint")}
          >
            {starterPrompts.slice(0, 3).map((prompt, index) => {
              const slot = starterSlotIcons[index]
              const SlotIcon = slot.icon
              return (
                <button
                  key={prompt}
                  type="button"
                  className={cn(
                    "group grid min-h-[32px] w-full grid-cols-[0.875rem_minmax(0,1fr)] items-center gap-2 rounded-[5px] px-4 text-left transition-colors duration-150 hover:bg-foreground/[0.025] focus-visible:relative focus-visible:z-10 focus-visible:bg-foreground/[0.035] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-foreground/18 focus-visible:ring-offset-1 focus-visible:ring-offset-background sm:min-h-[35px]",
                    index > 0 && "border-t border-border/75",
                  )}
                  onClick={() => {
                    setValue(prompt)
                    window.requestAnimationFrame(() =>
                      localTextareaRef.current?.focus(),
                    )
                  }}
                >
                  <SlotIcon
                    aria-hidden="true"
                    data-starter-slot-icon={slot.name}
                    className="size-3.5 text-muted-foreground/65 transition-colors duration-150 group-hover:text-muted-foreground/85"
                  />
                  <span className="min-w-0 truncate text-[12px] font-normal leading-[18px] tracking-normal text-muted-foreground transition-colors duration-150 group-hover:text-foreground/70 sm:text-[13px]">
                    {prompt}
                  </span>
                </button>
              )
            })}
          </section>
        ) : null}
      </div>

      {placement === "draft" && renderCommandDiscoveryHint ? (
        <AgentCommandDiscoveryHint visible={!value.trim()} />
      ) : null}

      {submitError ? (
        <p role="alert" className="text-sm text-destructive">
          {submitError}
        </p>
      ) : null}
      {stopError ? (
        <p role="alert" className="text-sm text-destructive">
          {stopError}
        </p>
      ) : null}
      {voice.state === "error" ? (
        <p role="alert" className="text-sm text-destructive">
          {t("voice.error")}
        </p>
      ) : null}
    </form>
  )
}
