"use client"

import { useRef, useState } from "react"
import { useTranslations } from "next-intl"

import { Loader2 } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  ConversationAskUserQuestion,
  ConversationInteractionRequest,
  ConversationInteractionResponse,
  InteractionTranscriptBlock,
} from "@/lib/agent/conversation-model/types"
import { cn } from "@/lib/utils"

type AgentInteractionCardProps = {
  interaction: InteractionTranscriptBlock
  actionable?: boolean
  expired?: boolean
  onRespond?: (response: ConversationInteractionResponse) => void | Promise<void>
}

type PendingAction =
  | "approve"
  | "reject"
  | "answers"
  | Extract<ConversationInteractionResponse, { type: "recovery" }>["choice"]
  | null

export function AgentInteractionCard({
  interaction,
  actionable,
  expired = false,
  onRespond,
}: AgentInteractionCardProps) {
  if (!interaction.request) return null
  return (
    <AgentInteractionCardState
      key={interaction.interactionId}
      interactionId={interaction.interactionId}
      request={interaction.request}
      response={interaction.response}
      actionable={actionable ?? Boolean(onRespond)}
      expired={expired}
      onRespond={onRespond}
    />
  )
}

function AgentInteractionCardState({
  interactionId,
  request,
  response,
  actionable,
  expired,
  onRespond,
}: {
  interactionId: string
  request: ConversationInteractionRequest
  response: ConversationInteractionResponse | null
  actionable: boolean
  expired: boolean
  onRespond?: (response: ConversationInteractionResponse) => void | Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const [answers, setAnswers] = useState<Record<string, string[]>>({})
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [submitFailed, setSubmitFailed] = useState(false)
  const submittingRef = useRef(false)
  const completed = response?.type === request.type
  const status = expired ? "expired" : interactionStatus(request, response)
  const tone = interactionTone(status)

  async function submit(nextResponse: ConversationInteractionResponse, action: PendingAction) {
    if (submittingRef.current || completed || !onRespond) return
    submittingRef.current = true
    setSubmitFailed(false)
    setPendingAction(action)
    try {
      await onRespond(nextResponse)
    } catch {
      submittingRef.current = false
      setPendingAction(null)
      setSubmitFailed(true)
    }
  }

  return (
    <section
      className={cn(
        "grid gap-4 rounded-[10px] border px-3.5 py-3 [content-visibility:auto] [contain-intrinsic-size:auto_160px]",
        tone === "warning" && "border-warning-border bg-warning-muted/25",
        tone === "success" && "border-success-border bg-success-muted/25",
        tone === "destructive" && "border-error-border bg-error-muted/25",
      )}
      data-interaction-id={interactionId}
      data-interaction-type={request.type}
      data-testid="agent-interaction-card"
    >
      {!completed && !expired ? (
        <p
          role="status"
          aria-live="polite"
          aria-atomic="true"
          className="sr-only"
        >
          {t(`${request.type}.announcement`)}
        </p>
      ) : null}
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-sm font-semibold text-foreground">
          {t(`${request.type}.title`)}
        </h2>
        <StatusBadge variant={tone}>{t(`status.${status}`)}</StatusBadge>
      </div>

      {request.type === "approval" ? (
        <ApprovalInteraction
          request={request}
          completed={completed || expired}
          pendingAction={pendingAction}
          canRespond={actionable && Boolean(onRespond)}
          onSubmit={submit}
        />
      ) : null}

      {request.type === "ask_user" ? (
        <AskUserInteraction
          interactionId={interactionId}
          request={request}
          response={response?.type === "ask_user" ? response : null}
          completed={completed || expired}
          answers={answers}
          pendingAction={pendingAction}
          canRespond={actionable && Boolean(onRespond)}
          onAnswersChange={setAnswers}
          onSubmit={submit}
        />
      ) : null}

      {request.type === "recovery" ? (
        <RecoveryInteraction
          request={request}
          response={response?.type === "recovery" ? response : null}
          completed={completed || expired}
          pendingAction={pendingAction}
          canRespond={actionable && Boolean(onRespond)}
          onSubmit={submit}
        />
      ) : null}

      {submitFailed ? (
        <p
          role="alert"
          aria-live="polite"
          className="rounded-[8px] border border-error-border bg-error-muted/55 px-3 py-2 text-xs leading-5 text-error-foreground"
        >
          {t("submit_failed")}
        </p>
      ) : null}
    </section>
  )
}

function ApprovalInteraction({
  request,
  completed,
  pendingAction,
  canRespond,
  onSubmit,
}: {
  request: Extract<ConversationInteractionRequest, { type: "approval" }>
  completed: boolean
  pendingAction: PendingAction
  canRespond: boolean
  onSubmit: (response: ConversationInteractionResponse, action: PendingAction) => Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const submitting = pendingAction !== null
  const escalated = request.risk.reasonCodes.includes("sandbox_escalation")
  const action = escalated
    ? t("approval.action.escalation")
    : approvalAction(request.toolName, t)
  const summary = request.summary.trim()

  return (
    <div className="grid gap-3.5">
      <div className="grid min-w-0 gap-1.5">
        <div className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          <p className="text-sm font-medium leading-5 text-foreground">
            {action}
          </p>
          <span
            className="rounded-[4px] border border-border/60 bg-background/55 px-1.5 py-0.5 font-mono text-[10px] leading-4 text-muted-foreground"
            translate="no"
          >
            {request.toolName}
          </span>
          {request.target ? (
            <>
              <span aria-hidden="true" className="text-muted-foreground/45">
                ·
              </span>
              <span className="font-medium text-foreground/72" translate="no">
                {request.target.displayName}
              </span>
              {request.target.host ? (
                <span className="font-mono" translate="no">
                  {request.target.host}
                </span>
              ) : null}
            </>
          ) : null}
        </div>
        {summary &&
        summary !== action &&
        summary !== defaultApprovalSummary(request.toolName) ? (
          <p className="text-xs leading-5 text-muted-foreground">{summary}</p>
        ) : null}
      </div>

      {request.inputPreview ? (
        <pre
          aria-label={t("approval.input")}
          className="max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-[8px] border border-border/70 bg-foreground/[0.035] px-3.5 py-3 font-mono text-sm leading-6 text-foreground dark:bg-background/55"
          data-testid="agent-approval-command"
          translate="no"
        >
          {request.inputPreview}
        </pre>
      ) : null}

      <RiskDetails request={request} />

      {!completed ? (
        <div className="flex flex-wrap justify-end gap-2 border-t border-border/55 pt-3">
          {request.allowedResponses.includes("reject") ? (
            <Button
              type="button"
              variant="outline"
              className="dark:bg-transparent dark:hover:bg-muted/35"
              disabled={submitting || !canRespond}
              onClick={() =>
                void onSubmit({ type: "approval", approved: false }, "reject")
              }
            >
              {pendingAction === "reject" ? (
                <SubmittingLabel />
              ) : (
                t("approval.reject")
              )}
            </Button>
          ) : null}
          {request.allowedResponses.includes("approve") ? (
            <Button
              type="button"
              disabled={submitting || !canRespond}
              onClick={() =>
                void onSubmit({ type: "approval", approved: true }, "approve")
              }
            >
              {pendingAction === "approve" ? (
                <SubmittingLabel />
              ) : (
                t("approval.approve")
              )}
            </Button>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}

type Translate = ReturnType<typeof useTranslations>

function approvalAction(toolName: string, t: Translate) {
  switch (toolName) {
    case "bash":
      return t("approval.action.command")
    case "write":
      return t("approval.action.write")
    case "edit":
      return t("approval.action.edit")
    case "read":
      return t("approval.action.read")
    default:
      return t("approval.action.tool", { toolName })
  }
}

type ApprovalEffectCode =
  | "read"
  | "write"
  | "delete"
  | "network"
  | "process_control"
  | "privilege"
  | "execute"

function approvalEffectCode(effect: string): ApprovalEffectCode | null {
  switch (effect) {
    case "read":
    case "write":
    case "delete":
    case "network":
    case "process_control":
    case "privilege":
    case "execute":
      return effect
    default:
      return null
  }
}

function approvalReasonCode(reason: string): "sandbox_escalation" | null {
  return reason === "sandbox_escalation" ? reason : null
}

function defaultApprovalSummary(toolName: string): string | null {
  switch (toolName) {
    case "bash":
      return "Run command"
    case "write":
      return "Write file"
    case "edit":
      return "Edit file"
    case "read":
      return "Read file"
    default:
      return null
  }
}

function RiskDetails({
  request,
}: {
  request: Extract<ConversationInteractionRequest, { type: "approval" }>
}) {
  const t = useTranslations("agentInteraction")
  const effects = request.risk.effects.map((effect) => {
    const code = approvalEffectCode(effect)
    return code ? t(`approval.effect.${code}`) : effect
  })
  const reasons = request.risk.reasonCodes.flatMap((reason) => {
    const code = approvalReasonCode(reason)
    return code ? [t(`approval.reason.${code}`)] : []
  })
  if (request.risk.justification) {
    reasons.push(
      t("approval.justification", {
        justification: request.risk.justification,
      }),
    )
  }
  const detailSections = [
    ["approval.reasons", reasons],
    ["approval.resources", request.risk.affectedResources],
  ] as const
  const hasDetails = detailSections.some(([, values]) => values.length > 0)

  return (
    <div className="grid gap-2.5">
      {effects.length > 0 ? (
        <ul
          aria-label={t("approval.effects")}
          className="flex flex-wrap gap-x-2.5 gap-y-1 text-xs leading-5 text-foreground/72"
          data-testid="agent-approval-effects"
        >
          {effects.map((effect, index) => (
            <li key={`${index}:${effect}`} className="break-words">
              {effect}
            </li>
          ))}
        </ul>
      ) : null}

      {hasDetails ? (
        <details className="group text-xs text-muted-foreground">
          <summary className="w-fit cursor-pointer select-none rounded-[4px] outline-none transition-colors hover:text-foreground focus-visible:ring-2 focus-visible:ring-ring/45 motion-reduce:transition-none">
            {t("approval.details")}
          </summary>
          <dl className="mt-2 grid gap-x-5 gap-y-2 border-l border-border/70 pl-3 sm:grid-cols-2">
            {detailSections.map(([label, values]) =>
              values.length > 0 ? (
                <div key={label} className="grid content-start gap-1">
                  <dt className="text-[11px] font-medium text-muted-foreground">
                    {t(label)}
                  </dt>
                  <dd>
                    <ul className="grid gap-1 text-xs leading-5 text-foreground/72">
                      {values.map((value, index) => (
                        <li key={`${index}:${value}`} className="break-words">
                          {value}
                        </li>
                      ))}
                    </ul>
                  </dd>
                </div>
              ) : null,
            )}
          </dl>
        </details>
      ) : null}
    </div>
  )
}

function AskUserInteraction({
  interactionId,
  request,
  response,
  completed,
  answers,
  pendingAction,
  canRespond,
  onAnswersChange,
  onSubmit,
}: {
  interactionId: string
  request: Extract<ConversationInteractionRequest, { type: "ask_user" }>
  response: Extract<ConversationInteractionResponse, { type: "ask_user" }> | null
  completed: boolean
  answers: Record<string, string[]>
  pendingAction: PendingAction
  canRespond: boolean
  onAnswersChange: (answers: Record<string, string[]>) => void
  onSubmit: (response: ConversationInteractionResponse, action: PendingAction) => Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const selectedAnswers = completed
    ? answersFromResponse(request.questions, response?.answers)
    : answers
  const ready =
    request.questions.length > 0 &&
    request.questions.every(
      (question) => (selectedAnswers[question.id]?.length ?? 0) > 0,
    )

  function updateAnswer(question: ConversationAskUserQuestion, optionId: string) {
    const current = answers[question.id] ?? []
    const next = question.multiSelect
      ? current.includes(optionId)
        ? current.filter((id) => id !== optionId)
        : [...current, optionId]
      : [optionId]
    onAnswersChange({ ...answers, [question.id]: next })
  }

  function submitAnswers() {
    const values: Extract<
      ConversationInteractionResponse,
      { type: "ask_user" }
    >["answers"] = {}
    for (const question of request.questions) {
      const selected = selectedAnswers[question.id] ?? []
      values[question.id] = question.multiSelect ? selected : selected[0] ?? null
    }
    return onSubmit({ type: "ask_user", answers: values }, "answers")
  }

  return (
    <div className="grid gap-0">
      {request.questions.map((question) => (
        <fieldset
          key={question.id}
          className="grid min-w-0 gap-3 border-0 border-t border-border/60 py-5 first:border-t-0 first:pt-0 last:pb-0"
          data-testid="agent-ask-question"
          disabled={completed || pendingAction !== null}
        >
          <legend className="w-full p-0 text-left">
            <span className="grid gap-1.5">
              <span className="min-w-0 [overflow-wrap:anywhere] text-[10px] font-medium uppercase tracking-[0.12em] text-muted-foreground">
                {question.header}
              </span>
              <span className="min-w-0 [overflow-wrap:anywhere] text-base font-semibold leading-6 tracking-[-0.01em] text-foreground">
                {question.question}
              </span>
            </span>
          </legend>
          <div
            className="divide-y divide-border/60 border-y border-border/60"
            data-testid="agent-ask-options"
          >
            {question.options.map((option, optionIndex) => {
              const selected = selectedAnswers[question.id]?.includes(option.id) ?? false
              return (
                <label
                  key={option.id}
                  className={cn(
                    "grid min-w-0 cursor-pointer grid-cols-[2rem_1.25rem_minmax(0,1fr)] items-start gap-x-2 px-1 py-3 transition-colors hover:bg-muted/20 focus-within:bg-muted/20 focus-within:outline-none focus-within:ring-2 focus-within:ring-inset focus-within:ring-ring/40",
                    selected && "bg-muted/30 dark:bg-muted/20",
                    completed && "cursor-default",
                  )}
                  data-testid="agent-ask-option"
                >
                  <span
                    aria-hidden="true"
                    className="pt-0.5 font-mono text-[10px] tabular-nums text-muted-foreground/70"
                  >
                    {String(optionIndex + 1).padStart(2, "0")}
                  </span>
                  <input
                    type={question.multiSelect ? "checkbox" : "radio"}
                    name={`${interactionId}:${question.id}`}
                    value={option.id}
                    checked={selected}
                    className="mt-0.5 size-4 shrink-0 accent-primary"
                    onChange={() => updateAnswer(question, option.id)}
                  />
                  <span className="grid min-w-0 gap-1 overflow-hidden">
                    <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1 text-sm font-medium text-foreground">
                      <span className="min-w-0 [overflow-wrap:anywhere] text-sm font-medium">
                        {option.label}
                      </span>
                      {option.recommended ? (
                        <StatusBadge
                          variant="neutral"
                          className="px-1.5 py-0 text-[9px] uppercase tracking-[0.08em]"
                        >
                          {t("ask_user.recommended")}
                        </StatusBadge>
                      ) : null}
                    </span>
                    {option.description ? (
                      <span className="min-w-0 [overflow-wrap:anywhere] text-xs leading-5 text-muted-foreground">
                        {option.description}
                      </span>
                    ) : null}
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>
      ))}

      {!completed ? (
        <div className="flex justify-end pt-4">
          <Button
            type="button"
            disabled={!ready || pendingAction !== null || !canRespond}
            onClick={() => void submitAnswers()}
          >
            {pendingAction === "answers" ? <SubmittingLabel /> : t("ask_user.submit")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function RecoveryInteraction({
  request,
  response,
  completed,
  pendingAction,
  canRespond,
  onSubmit,
}: {
  request: Extract<ConversationInteractionRequest, { type: "recovery" }>
  response: Extract<ConversationInteractionResponse, { type: "recovery" }> | null
  completed: boolean
  pendingAction: PendingAction
  canRespond: boolean
  onSubmit: (response: ConversationInteractionResponse, action: PendingAction) => Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const optionById = new Map(request.options.map((option) => [option.id, option]))
  const choices = recoveryChoices(request.options.map((option) => option.id))
  const messageCode = knownRecoveryMessageCode(request.messageCode)
  const stableBackendCopy = messageCode !== null

  function optionLabel(choice: (typeof choices)[number]) {
    return stableBackendCopy
      ? t(`recovery.option.${choice}.label`)
      : optionById.get(choice)?.label ?? t(`recovery.${choice}`)
  }

  function optionDescription(choice: (typeof choices)[number]) {
    return stableBackendCopy
      ? t(`recovery.option.${choice}.description`)
      : optionById.get(choice)?.description ?? ""
  }

  return (
    <div className="grid gap-3">
      <p className="text-sm leading-6 text-foreground/85">
        {messageCode
          ? t(`recovery.message.${messageCode}`, {
              toolName: request.messageParams.tool_name ?? request.toolName,
            })
          : request.messageFallback}
      </p>

      {completed && response ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{t("recovery.selected")}</span>
          <span className="font-medium text-foreground">
            {optionLabel(response.choice)}
          </span>
        </div>
      ) : (
        <>
          <dl className="grid gap-2 sm:grid-cols-3">
            {choices.map((choice) => {
              const description = optionDescription(choice)
              if (!description) return null
              return (
                <div key={choice} className="grid content-start gap-0.5">
                  <dt className="text-xs font-medium text-foreground/80">
                    {optionLabel(choice)}
                  </dt>
                  <dd className="text-xs leading-5 text-muted-foreground">
                    {description}
                  </dd>
                </div>
              )
            })}
          </dl>
          <div className="flex flex-wrap justify-end gap-2">
            {choices.map((choice) => {
              const label = optionLabel(choice)
              return (
                <Button
                  key={choice}
                  type="button"
                  variant={choice === "retry" ? "default" : "outline"}
                  className={cn(
                    choice !== "retry" &&
                      "dark:bg-transparent dark:hover:bg-muted/35",
                  )}
                  disabled={pendingAction !== null || !canRespond}
                  aria-label={pendingAction === choice ? t("submitting") : label}
                  onClick={() =>
                    void onSubmit({ type: "recovery", choice }, choice)
                  }
                >
                  {pendingAction === choice ? <SubmittingLabel /> : label}
                </Button>
              )
            })}
          </div>
        </>
      )}
    </div>
  )
}

function knownRecoveryMessageCode(code: string | null) {
  return code === "unknown_tool_effect" ? code : null
}

function recoveryChoices(optionIds: string[]) {
  const choices: Extract<ConversationInteractionResponse, { type: "recovery" }>["choice"][] = []
  const seen = new Set<string>()
  for (const optionId of optionIds) {
    if (
      seen.has(optionId) ||
      !["inspect", "retry", "cancel"].includes(optionId)
    ) {
      continue
    }
    seen.add(optionId)
    choices.push(optionId as Extract<ConversationInteractionResponse, { type: "recovery" }>["choice"])
  }
  return choices
}

function SubmittingLabel() {
  const t = useTranslations("agentInteraction")
  return (
    <>
      <Loader2 data-icon="inline-start" aria-hidden="true" className="animate-spin motion-reduce:animate-none" />
      {t("submitting")}
    </>
  )
}

function answersFromResponse(
  questions: ConversationAskUserQuestion[],
  answers?: Extract<
    ConversationInteractionResponse,
    { type: "ask_user" }
  >["answers"],
) {
  const selected: Record<string, string[]> = {}
  for (const question of questions) {
    const value = answers?.[question.id]
    if (typeof value === "string") {
      selected[question.id] = [value]
    } else if (Array.isArray(value)) {
      selected[question.id] = value.filter(
        (item): item is string => typeof item === "string",
      )
    }
  }
  return selected
}

function interactionStatus(
  request: ConversationInteractionRequest,
  response?: ConversationInteractionResponse | null,
) {
  if (!response || response.type !== request.type) return "pending" as const
  if (response.type === "approval") {
    return response.approved ? ("approved" as const) : ("rejected" as const)
  }
  if (response.type === "ask_user") return "answered" as const
  return "resolved" as const
}

function interactionTone(status: ReturnType<typeof interactionStatus> | "expired") {
  if (status === "pending" || status === "expired") return "warning" as const
  if (status === "rejected") return "destructive" as const
  return "success" as const
}
