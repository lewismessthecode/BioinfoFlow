"use client"

import { useState } from "react"
import { Check, CircleHelp, Edit3 } from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { AgentAnswer, AgentAskUserQuestion } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import type { AgentDecisionHandler } from "./types"
import { DecisionSubmissionFeedback, useDecisionSubmission } from "./decision-submission"

type AskUserDecisionCardProps = {
  actionId: string
  questions: AgentAskUserQuestion[]
  onDecision?: AgentDecisionHandler
  inline?: boolean
  id?: string
  testId?: string
  answer?: AgentAnswer | null
  readOnly?: boolean
  stateLabel?: string | null
}

export function AskUserDecisionCard({
  actionId,
  questions,
  onDecision,
  inline = false,
  id,
  testId = "ask-user-card",
  answer = null,
  readOnly = false,
  stateLabel = null,
}: AskUserDecisionCardProps) {
  const t = useTranslations("agentRuntime")
  const [selections, setSelections] = useState<Record<string, string[]>>({})
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({})
  const submission = useDecisionSubmission(actionId, onDecision)
  const effectiveReadOnly = readOnly || submission.busy

  const toggle = (question: AgentAskUserQuestion, label: string) => {
    setSelections((current) => {
      const existing = current[question.header] ?? []
      if (question.multiSelect) {
        const next = existing.includes(label)
          ? existing.filter((item) => item !== label)
          : [...existing, label]
        return { ...current, [question.header]: next }
      }
      return { ...current, [question.header]: [label] }
    })
    if (!question.multiSelect) {
      setCustomAnswers((current) => ({ ...current, [question.header]: "" }))
    }
  }

  const updateCustomAnswer = (question: AgentAskUserQuestion, value: string) => {
    setCustomAnswers((current) => ({ ...current, [question.header]: value }))
    if (!question.multiSelect && value.trim()) {
      setSelections((current) => ({ ...current, [question.header]: [] }))
    }
  }

  const hasAnswer = (question: AgentAskUserQuestion) => {
    const picked = selections[question.header] ?? []
    const customAnswer = customAnswers[question.header]?.trim() ?? ""
    return picked.length > 0 || customAnswer.length > 0
  }

  const complete = questions.every(hasAnswer)
  const canSubmit = !effectiveReadOnly && complete && Boolean(onDecision)

  const submit = () => {
    const answer: AgentAnswer = {}
    for (const question of questions) {
      const picked = selections[question.header] ?? []
      const customAnswer = customAnswers[question.header]?.trim() ?? ""

      if (question.multiSelect) {
        answer[question.header] = customAnswer ? [...picked, customAnswer] : picked
      } else {
        answer[question.header] = customAnswer || picked[0] || ""
      }
    }
    void submission.submit("answer", { answer })
  }

  return (
    <div
      id={id}
      className={cn(
        "rounded-lg border border-border/55 bg-muted/[0.18] px-3 py-2.5 text-sm text-muted-foreground",
        inline && "mb-3",
      )}
      data-testid={testId}
    >
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <CircleHelp className="h-3.5 w-3.5 shrink-0" />
        <span className="font-medium text-foreground/65">{t("ask.title")}</span>
        {stateLabel ? <span className="ml-auto text-[11px]">{stateLabel}</span> : null}
      </div>

      <div className="grid gap-3">
        {questions.map((question, questionIndex) => {
          const customId = `${actionId}-${questionIndex}-custom-answer`
          const answeredValue = answer?.[question.header]
          const answeredLabels = Array.isArray(answeredValue)
            ? answeredValue
            : answeredValue
              ? [answeredValue]
              : []
          return (
            <div key={question.header} className="grid gap-2">
              <div className="text-[13px] leading-5 text-foreground/80">
                {question.question}
              </div>
              <div className="grid gap-1">
                {question.options.map((option, optionIndex) => {
                  const active = readOnly
                    ? answeredLabels.includes(option.label)
                    : (selections[question.header] ?? []).includes(option.label)
                  return (
                    <button
                      key={option.label}
                      type="button"
                      aria-pressed={active}
                      disabled={effectiveReadOnly}
                      onClick={() => toggle(question, option.label)}
                      className={cn(
                        "group flex min-h-9 items-start gap-2 rounded-md border px-2 py-1.5 text-left transition-colors",
                        active
                          ? "border-foreground/18 bg-background text-foreground/85"
                          : "border-border/60 bg-background/55 text-muted-foreground hover:border-foreground/15 hover:bg-background/80",
                        readOnly && "cursor-default hover:border-border/60 hover:bg-background/55",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 flex h-[18px] w-[18px] shrink-0 items-center justify-center rounded-full border text-[10px]",
                          active
                            ? "border-foreground/40 bg-foreground text-background"
                            : "border-border bg-muted/45 text-muted-foreground",
                        )}
                      >
                        {optionIndex + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="break-words text-foreground/75">
                            {option.label}
                          </span>
                          {option.recommended ? (
                            <Badge
                              variant="secondary"
                              className="h-5 rounded-full border-border bg-muted/60 px-1.5 text-[10px] text-muted-foreground"
                            >
                              {t("ask.recommended")}
                            </Badge>
                          ) : null}
                        </span>
                        {option.description ? (
                          <span className="mt-0.5 block break-words text-xs leading-5 text-muted-foreground">
                            {option.description}
                          </span>
                        ) : null}
                      </span>
                      {active ? (
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-muted-foreground" />
                      ) : null}
                    </button>
                  )
                })}
              </div>

              {readOnly ? (
                answeredLabels.length ? (
                  <div className="flex min-w-0 flex-wrap items-center gap-1.5 text-xs text-muted-foreground">
                    <span className="shrink-0">{t("ask.answerLabel")}</span>
                    {answeredLabels.map((item) => (
                      <span
                        key={item}
                        className="min-w-0 max-w-full break-all rounded-md bg-muted px-1.5 py-0.5 font-mono text-[11px] text-foreground/70"
                      >
                        {item}
                      </span>
                    ))}
                  </div>
                ) : null
              ) : (
                <label
                  htmlFor={customId}
                  className="flex min-h-9 items-center gap-2 rounded-md border border-dashed border-border/70 bg-background/55 px-2 py-1 focus-within:border-foreground/25 focus-within:ring-2 focus-within:ring-ring/20"
                >
                  <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full border border-border bg-muted/45 text-muted-foreground">
                    <Edit3 className="h-3.5 w-3.5" />
                  </span>
                  <span className="shrink-0 text-xs text-muted-foreground">
                    {t("ask.customLabel")}
                  </span>
                  <Input
                    id={customId}
                    name={customId}
                    autoComplete="off"
                    value={customAnswers[question.header] ?? ""}
                    onChange={(event) => updateCustomAnswer(question, event.target.value)}
                    disabled={effectiveReadOnly}
                    placeholder={t("ask.customPlaceholder")}
                    className="h-7 border-0 bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
                  />
                </label>
              )}
            </div>
          )
        })}
      </div>

      {!readOnly ? <div className="mt-3 flex items-center justify-end gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 rounded-full text-muted-foreground"
          disabled={!onDecision || submission.busy}
          onClick={() => void submission.submit("reject")}
        >
          {t("ask.rejectQuestion")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="secondary"
          className="h-8 rounded-full"
          disabled={!canSubmit}
          onClick={submit}
        >
          {t("ask.submit")}
        </Button>
      </div> : null}
      {!readOnly ? (
        <DecisionSubmissionFeedback
          busy={submission.busy}
          error={submission.error}
          onRetry={() => void submission.retry()}
        />
      ) : null}
    </div>
  )
}
