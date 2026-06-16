"use client"

import { useState } from "react"
import { Check, CheckCircle2, XCircle } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentAnswer, AgentAskUserQuestion } from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import type { AgentDecisionCard } from "./pending-actions"
import type { AgentDecisionHandler } from "./types"

export function InlineApprovalCard({
  decision,
  onDecision,
}: {
  decision: AgentDecisionCard
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  const isPending = decision.state === "pending"

  if (isPending && decision.interaction?.kind === "user_input") {
    return (
      <InlineAskUserCard
        actionId={decision.actionId}
        questions={decision.interaction.questions}
        onDecision={onDecision}
      />
    )
  }

  return (
    <div
      className="mb-3 rounded-2xl border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm"
      data-testid="inline-approval-card"
    >
      <div className="mb-2 flex items-center gap-2 font-medium text-amber-900 dark:text-amber-200">
        {isPending ? <Check className="h-4 w-4" /> : <DecisionStateIcon state={decision.state} />}
        <span className="min-w-0 flex-1">
          {isPending ? t("sidecar.needsDecision") : t(`approval.state.${decision.state}`)}
        </span>
        {decision.riskLevel ? (
          <span className="rounded-full bg-amber-500/20 px-2 py-0.5 text-[10px] uppercase tracking-wide">
            {decision.riskLevel}
          </span>
        ) : null}
      </div>

      <div className="grid gap-1.5 text-xs text-amber-900/80 dark:text-amber-100/80">
        <div className="font-mono">{decision.name ?? decision.actionId}</div>
        {decision.inputPreview ? (
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-xl bg-background/60 p-2 font-mono">
            {decision.inputPreview}
          </pre>
        ) : null}
      </div>

      {isPending && onDecision ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            className="h-8 rounded-full"
            onClick={() => onDecision(decision.actionId, "approve")}
          >
            <Check className="h-3.5 w-3.5" />
            {t("approve")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card"
            onClick={() => onDecision(decision.actionId, "reject")}
          >
            {t("reject")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function InlineAskUserCard({
  actionId,
  questions,
  onDecision,
}: {
  actionId: string
  questions: AgentAskUserQuestion[]
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  const [selections, setSelections] = useState<Record<string, string[]>>({})

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
  }

  const complete = questions.every(
    (question) => (selections[question.header]?.length ?? 0) > 0,
  )

  const submit = () => {
    const answer: AgentAnswer = {}
    for (const question of questions) {
      const picked = selections[question.header] ?? []
      answer[question.header] = question.multiSelect ? picked : picked[0] ?? ""
    }
    onDecision?.(actionId, "answer", { answer })
  }

  return (
    <div
      className="mb-3 rounded-2xl border border-sky-500/30 bg-sky-500/10 px-3 py-3 text-sm"
      data-testid="inline-ask-user-card"
    >
      <div className="mb-2 font-medium text-sky-900 dark:text-sky-200">
        {t("ask.title")}
      </div>
      <div className="grid gap-3">
        {questions.map((question) => (
          <div key={question.header} className="grid gap-1.5">
            <div className="text-xs font-medium text-foreground">{question.question}</div>
            <div className="grid gap-1.5">
              {question.options.map((option) => {
                const active = (selections[question.header] ?? []).includes(option.label)
                return (
                  <button
                    key={option.label}
                    type="button"
                    onClick={() => toggle(question, option.label)}
                    className={cn(
                      "flex flex-col items-start rounded-xl border px-2.5 py-1.5 text-left transition-colors",
                      active
                        ? "border-primary bg-primary/10"
                        : "border-border/60 bg-card hover:bg-muted/40",
                    )}
                  >
                    <span className="text-sm font-medium text-foreground">{option.label}</span>
                    {option.description ? (
                      <span className="text-xs text-muted-foreground">{option.description}</span>
                    ) : null}
                  </button>
                )
              })}
            </div>
          </div>
        ))}
      </div>
      <div className="mt-3">
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-full"
          disabled={!complete || !onDecision}
          onClick={submit}
        >
          {t("ask.submit")}
        </Button>
      </div>
    </div>
  )
}

function DecisionStateIcon({ state }: { state: AgentDecisionCard["state"] }) {
  if (state === "rejected") return <XCircle className="h-4 w-4" />
  return <CheckCircle2 className="h-4 w-4" />
}
