"use client"

import { useRef, useState } from "react"
import { useTranslations } from "next-intl"

import { Loader2 } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import { StatusBadge } from "@/components/ui/status-badge"
import type {
  AskUserQuestion,
  InteractionRequest,
  InteractionResponse,
  JsonObject,
  RecoveryInteractionResponse,
} from "@/lib/agent/contracts"
import { cn } from "@/lib/utils"

type AgentInteractionCardProps = {
  interactionId: string
  request: InteractionRequest
  response?: InteractionResponse | null
  onRespond?: (response: InteractionResponse) => void | Promise<void>
}

type PendingAction =
  | "approve"
  | "reject"
  | "answers"
  | RecoveryInteractionResponse["choice"]
  | null

export function AgentInteractionCard({
  ...props
}: AgentInteractionCardProps) {
  return <AgentInteractionCardState key={props.interactionId} {...props} />
}

function AgentInteractionCardState({
  interactionId,
  request,
  response,
  onRespond,
}: AgentInteractionCardProps) {
  const t = useTranslations("agentInteraction")
  const [answers, setAnswers] = useState<Record<string, string[]>>({})
  const [pendingAction, setPendingAction] = useState<PendingAction>(null)
  const [submitFailed, setSubmitFailed] = useState(false)
  const submittingRef = useRef(false)
  const completed = response?.type === request.type
  const status = interactionStatus(request, response)
  const tone = interactionTone(status)

  async function submit(nextResponse: InteractionResponse, action: PendingAction) {
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
      {!completed ? (
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
          completed={completed}
          pendingAction={pendingAction}
          canRespond={Boolean(onRespond)}
          onSubmit={submit}
        />
      ) : null}

      {request.type === "ask_user" ? (
        <AskUserInteraction
          interactionId={interactionId}
          request={request}
          response={response?.type === "ask_user" ? response : null}
          completed={completed}
          answers={answers}
          pendingAction={pendingAction}
          canRespond={Boolean(onRespond)}
          onAnswersChange={setAnswers}
          onSubmit={submit}
        />
      ) : null}

      {request.type === "recovery" ? (
        <RecoveryInteraction
          request={request}
          response={response?.type === "recovery" ? response : null}
          completed={completed}
          pendingAction={pendingAction}
          canRespond={Boolean(onRespond)}
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
  request: Extract<InteractionRequest, { type: "approval" }>
  completed: boolean
  pendingAction: PendingAction
  canRespond: boolean
  onSubmit: (response: InteractionResponse, action: PendingAction) => Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const submitting = pendingAction !== null

  return (
    <div className="grid gap-3">
      <div className="flex flex-wrap items-start justify-between gap-2">
        <p className="min-w-0 flex-1 text-sm leading-6 text-foreground/85">
          {request.summary}
        </p>
        <span
          className="shrink-0 rounded-[5px] border border-border/60 bg-background/70 px-2 py-1 font-mono text-[10px] uppercase tracking-[0.08em] text-muted-foreground"
          translate="no"
        >
          {request.risk.level}
        </span>
      </div>

      {request.input_preview ? (
        <div className="grid gap-1.5">
          <h3 className="text-xs font-medium text-muted-foreground">
            {t("approval.input")}
          </h3>
          <pre
            className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-[8px] bg-background/75 px-3 py-2 font-mono text-xs leading-5 text-foreground/75"
            translate="no"
          >
            {request.input_preview}
          </pre>
        </div>
      ) : null}

      <RiskDetails request={request} />

      {!completed ? (
        <div className="flex flex-wrap justify-end gap-2">
          {request.allowed_responses.includes("reject") ? (
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
          {request.allowed_responses.includes("approve") ? (
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

function RiskDetails({
  request,
}: {
  request: Extract<InteractionRequest, { type: "approval" }>
}) {
  const t = useTranslations("agentInteraction")
  const sections = [
    ["approval.effects", request.risk.effects],
    ["approval.reasons", request.risk.reasons],
    ["approval.resources", request.risk.affected_resources],
  ] as const

  return (
    <div className="grid gap-2 sm:grid-cols-3">
      {sections.map(([label, values]) =>
        values.length > 0 ? (
          <div key={label} className="grid content-start gap-1">
            <h3 className="text-[11px] font-medium text-muted-foreground">
              {t(label)}
            </h3>
            <ul className="grid gap-1 text-xs leading-5 text-foreground/72">
              {values.map((value, index) => (
                <li key={`${index}:${value}`} className="break-words">
                  {value}
                </li>
              ))}
            </ul>
          </div>
        ) : null,
      )}
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
  request: Extract<InteractionRequest, { type: "ask_user" }>
  response: Extract<InteractionResponse, { type: "ask_user" }> | null
  completed: boolean
  answers: Record<string, string[]>
  pendingAction: PendingAction
  canRespond: boolean
  onAnswersChange: (answers: Record<string, string[]>) => void
  onSubmit: (response: InteractionResponse, action: PendingAction) => Promise<void>
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

  function updateAnswer(question: AskUserQuestion, optionId: string) {
    const current = answers[question.id] ?? []
    const next = question.multi_select
      ? current.includes(optionId)
        ? current.filter((id) => id !== optionId)
        : [...current, optionId]
      : [optionId]
    onAnswersChange({ ...answers, [question.id]: next })
  }

  function submitAnswers() {
    const values: JsonObject = {}
    for (const question of request.questions) {
      const selected = selectedAnswers[question.id] ?? []
      values[question.id] = question.multi_select ? selected : selected[0] ?? null
    }
    return onSubmit({ type: "ask_user", answers: values }, "answers")
  }

  return (
    <div className="grid gap-4">
      {request.questions.map((question) => (
        <fieldset
          key={question.id}
          className="grid gap-2 border-0 p-0"
          disabled={completed || pendingAction !== null}
        >
          <legend className="grid gap-0.5 text-sm font-medium text-foreground">
            <span>{question.header}</span>
            <span className="text-xs font-normal leading-5 text-muted-foreground">
              {question.question}
            </span>
          </legend>
          <div className="grid gap-2 sm:grid-cols-2">
            {question.options.map((option) => {
              const selected = selectedAnswers[question.id]?.includes(option.id) ?? false
              return (
                <label
                  key={option.id}
                  className={cn(
                    "flex min-w-0 cursor-pointer items-start gap-2.5 rounded-[8px] border border-border/60 bg-background/70 px-3 py-2.5 transition-colors hover:border-foreground/20 hover:bg-background focus-within:border-ring focus-within:ring-2 focus-within:ring-ring/35",
                    selected && "border-foreground/25 bg-background",
                    completed && "cursor-default",
                  )}
                >
                  <input
                    type={question.multi_select ? "checkbox" : "radio"}
                    name={`${interactionId}:${question.id}`}
                    value={option.id}
                    checked={selected}
                    className="mt-0.5 size-4 shrink-0 accent-primary"
                    onChange={() => updateAnswer(question, option.id)}
                  />
                  <span className="grid min-w-0 flex-1 gap-0.5">
                    <span className="flex flex-wrap items-center gap-2 text-xs font-medium text-foreground">
                      {option.label}
                      {option.recommended ? (
                        <StatusBadge variant="neutral" className="px-1.5 py-0 text-[10px]">
                          {t("ask_user.recommended")}
                        </StatusBadge>
                      ) : null}
                    </span>
                    <span className="text-xs leading-5 text-muted-foreground">
                      {option.description}
                    </span>
                  </span>
                </label>
              )
            })}
          </div>
        </fieldset>
      ))}

      {!completed ? (
        <div className="flex justify-end">
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
  request: Extract<InteractionRequest, { type: "recovery" }>
  response: Extract<InteractionResponse, { type: "recovery" }> | null
  completed: boolean
  pendingAction: PendingAction
  canRespond: boolean
  onSubmit: (response: InteractionResponse, action: PendingAction) => Promise<void>
}) {
  const t = useTranslations("agentInteraction")
  const optionById = new Map(request.options.map((option) => [option.id, option]))
  const choices = recoveryChoices(request.options.map((option) => option.id))

  return (
    <div className="grid gap-3">
      <p className="text-sm leading-6 text-foreground/85">{request.message}</p>

      {completed && response ? (
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span>{t("recovery.selected")}</span>
          <span className="font-medium text-foreground">
            {optionById.get(response.choice)?.label ?? t(`recovery.${response.choice}`)}
          </span>
        </div>
      ) : (
        <>
          <dl className="grid gap-2 sm:grid-cols-3">
            {choices.map((choice) => {
              const option = optionById.get(choice)
              if (!option?.description) return null
              return (
                <div key={choice} className="grid content-start gap-0.5">
                  <dt className="text-xs font-medium text-foreground/80">
                    {option.label}
                  </dt>
                  <dd className="text-xs leading-5 text-muted-foreground">
                    {option.description}
                  </dd>
                </div>
              )
            })}
          </dl>
          <div className="flex flex-wrap justify-end gap-2">
            {choices.map((choice) => {
              const label = optionById.get(choice)?.label ?? t(`recovery.${choice}`)
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

function recoveryChoices(optionIds: string[]) {
  const choices: RecoveryInteractionResponse["choice"][] = []
  const seen = new Set<string>()
  for (const optionId of optionIds) {
    if (
      seen.has(optionId) ||
      !["inspect", "retry", "cancel"].includes(optionId)
    ) {
      continue
    }
    seen.add(optionId)
    choices.push(optionId as RecoveryInteractionResponse["choice"])
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
  questions: AskUserQuestion[],
  answers?: JsonObject,
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
  request: InteractionRequest,
  response?: InteractionResponse | null,
) {
  if (!response || response.type !== request.type) return "pending" as const
  if (response.type === "approval") {
    return response.approved ? ("approved" as const) : ("rejected" as const)
  }
  if (response.type === "ask_user") return "answered" as const
  return "resolved" as const
}

function interactionTone(status: ReturnType<typeof interactionStatus>) {
  if (status === "pending") return "warning" as const
  if (status === "rejected") return "destructive" as const
  return "success" as const
}
