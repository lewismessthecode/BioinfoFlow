"use client"

import { useState } from "react"
import { Check, Edit3 } from "lucide-react"
import { useTranslations } from "next-intl"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import type { AgentAnswer, AgentAskUserQuestion } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import type { AgentDecisionHandler } from "./types"

type AskUserDecisionCardProps = {
  actionId: string
  questions: AgentAskUserQuestion[]
  onDecision?: AgentDecisionHandler
  inline?: boolean
  id?: string
  testId?: string
}

export function AskUserDecisionCard({
  actionId,
  questions,
  onDecision,
  inline = false,
  id,
  testId = "ask-user-card",
}: AskUserDecisionCardProps) {
  const t = useTranslations("agentRuntime")
  const [selections, setSelections] = useState<Record<string, string[]>>({})
  const [customAnswers, setCustomAnswers] = useState<Record<string, string>>({})

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
    setCustomAnswers((current) => ({ ...current, [question.header]: "" }))
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
    onDecision?.(actionId, "answer", { answer })
  }

  return (
    <div
      id={id}
      className={cn(
        "rounded-2xl border border-cyan-500/25 bg-cyan-500/[0.07] px-3 py-3 text-sm shadow-[0_14px_35px_-28px_rgba(8,145,178,0.75)]",
        inline && "mb-3",
      )}
      data-testid={testId}
    >
      <div className="mb-3 flex items-center gap-2 text-xs font-medium text-cyan-900/80 dark:text-cyan-100/80">
        <span className="h-1.5 w-1.5 rounded-full bg-cyan-500 shadow-[0_0_0_3px_rgba(6,182,212,0.12)]" />
        <span>{t("ask.title")}</span>
      </div>

      <div className="grid gap-4">
        {questions.map((question, questionIndex) => {
          const customId = `${actionId}-${questionIndex}-custom-answer`
          return (
            <div key={question.header} className="grid gap-2">
              <div className="text-[13px] font-semibold leading-5 text-foreground">
                {question.question}
              </div>
              <div className="grid gap-1.5">
                {question.options.map((option, optionIndex) => {
                  const active = (selections[question.header] ?? []).includes(option.label)
                  return (
                    <button
                      key={option.label}
                      type="button"
                      aria-pressed={active}
                      onClick={() => toggle(question, option.label)}
                      className={cn(
                        "group flex min-h-11 items-start gap-2 rounded-lg border px-2.5 py-2 text-left transition-[background-color,border-color,box-shadow]",
                        active
                          ? "border-cyan-500/70 bg-background shadow-[inset_3px_0_0_rgb(6,182,212)]"
                          : "border-border/70 bg-background/80 hover:border-cyan-500/40 hover:bg-background",
                      )}
                    >
                      <span
                        className={cn(
                          "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-semibold",
                          active
                            ? "border-cyan-900 bg-cyan-950 text-white dark:border-cyan-200 dark:bg-cyan-100 dark:text-cyan-950"
                            : "border-border bg-muted/60 text-muted-foreground",
                        )}
                      >
                        {optionIndex + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="flex flex-wrap items-center gap-1.5">
                          <span className="break-words font-medium text-foreground">
                            {option.label}
                          </span>
                          {option.recommended ? (
                            <Badge
                              variant="secondary"
                              className="h-5 rounded-full border-cyan-500/20 bg-cyan-500/10 px-1.5 text-[10px] text-cyan-900 dark:text-cyan-100"
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
                        <Check className="mt-0.5 h-4 w-4 shrink-0 text-cyan-700 dark:text-cyan-200" />
                      ) : null}
                    </button>
                  )
                })}
              </div>

              <label
                htmlFor={customId}
                className="flex min-h-11 items-center gap-2 rounded-lg border border-dashed border-border/80 bg-background/75 px-2.5 py-1.5 focus-within:border-cyan-500/60 focus-within:ring-2 focus-within:ring-cyan-500/15"
              >
                <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-border bg-muted/60 text-muted-foreground">
                  <Edit3 className="h-3.5 w-3.5" />
                </span>
                <span className="sr-only">{t("ask.customLabel")}</span>
                <Input
                  id={customId}
                  value={customAnswers[question.header] ?? ""}
                  onChange={(event) => updateCustomAnswer(question, event.target.value)}
                  placeholder={t("ask.customPlaceholder")}
                  className="h-8 border-0 bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
                />
              </label>
            </div>
          )
        })}
      </div>

      <div className="mt-3 flex items-center justify-end gap-2">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-8 rounded-full text-muted-foreground"
          disabled={!onDecision}
          onClick={() => onDecision?.(actionId, "reject")}
        >
          {t("ask.skip")}
        </Button>
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-full bg-cyan-600 text-white hover:bg-cyan-700"
          disabled={!complete || !onDecision}
          onClick={submit}
        >
          {t("ask.submit")}
        </Button>
      </div>
    </div>
  )
}
