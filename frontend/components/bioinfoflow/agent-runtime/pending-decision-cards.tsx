"use client"

import { useMemo, useState } from "react"
import { Check } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type {
  AgentAnswer,
  AgentAskUserQuestion,
  AgentRuntimeEvent,
  AgentWaitingDecision,
} from "@/lib/agent-runtime"
import { cn } from "@/lib/utils"
import { getPendingActions, parseWaitingDecision } from "./pending-actions"
import type { AgentDecisionHandler } from "./types"

export function PendingDecisionCards({
  events,
  onDecision,
}: {
  events: AgentRuntimeEvent[]
  onDecision: AgentDecisionHandler
}) {
  const decisions = useMemo(
    () => getPendingActions(events).map(parseWaitingDecision),
    [events],
  )
  if (!decisions.length) return null
  return (
    <div className="grid gap-3" data-testid="pending-decisions">
      {decisions.map((decision) => (
        <DecisionCard key={decision.actionId} decision={decision} onDecision={onDecision} />
      ))}
    </div>
  )
}

function DecisionCard({
  decision,
  onDecision,
}: {
  decision: AgentWaitingDecision
  onDecision: AgentDecisionHandler
}) {
  if (decision.interaction?.kind === "user_input") {
    return (
      <AskUserCard
        actionId={decision.actionId}
        questions={decision.interaction.questions}
        onDecision={onDecision}
      />
    )
  }
  if (decision.interaction?.kind === "plan_approval") {
    return (
      <PlanApprovalCard
        actionId={decision.actionId}
        plan={decision.interaction.plan}
        onDecision={onDecision}
      />
    )
  }
  return <ApprovalCard decision={decision} onDecision={onDecision} />
}

function ApprovalCard({
  decision,
  onDecision,
}: {
  decision: AgentWaitingDecision
  onDecision: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  return (
    <div className="rounded-[18px] border border-amber-500/30 bg-amber-500/10 px-3 py-3 text-sm">
      <div className="mb-1 font-medium text-amber-900 dark:text-amber-200">
        {t("sidecar.needsDecision")}
      </div>
      <div className="mb-1 font-mono text-xs text-amber-800/80 dark:text-amber-100/80">
        {decision.name ?? decision.actionId}
        {decision.riskLevel ? (
          <span className="ml-2 rounded-full bg-amber-500/20 px-1.5 py-0.5">
            {decision.riskLevel}
          </span>
        ) : null}
      </div>
      {decision.inputPreview ? (
        <div className="mb-3 truncate font-mono text-xs text-amber-800/70 dark:text-amber-100/70">
          {decision.inputPreview}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
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
    </div>
  )
}

function PlanApprovalCard({
  actionId,
  plan,
  onDecision,
}: {
  actionId: string
  plan: string
  onDecision: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  return (
    <div className="rounded-[18px] border border-primary/30 bg-primary/5 px-3 py-3 text-sm" data-testid="plan-approval-card">
      <div className="mb-2 font-medium text-foreground">{t("plan.reviewTitle")}</div>
      <pre className="mb-3 max-h-60 overflow-auto whitespace-pre-wrap break-words rounded-xl border border-border/60 bg-card p-2.5 text-xs leading-5 text-foreground">
        {plan || "—"}
      </pre>
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-full"
          onClick={() => onDecision(actionId, "approve")}
        >
          <Check className="h-3.5 w-3.5" />
          {t("plan.approveAndAct")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 rounded-full bg-card"
          onClick={() => onDecision(actionId, "reject")}
        >
          {t("plan.keepPlanning")}
        </Button>
      </div>
    </div>
  )
}

function AskUserCard({
  actionId,
  questions,
  onDecision,
}: {
  actionId: string
  questions: AgentAskUserQuestion[]
  onDecision: AgentDecisionHandler
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
    onDecision(actionId, "answer", { answer })
  }

  return (
    <div className="rounded-[18px] border border-sky-500/30 bg-sky-500/10 px-3 py-3 text-sm" data-testid="ask-user-card">
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
                    aria-pressed={active}
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
          disabled={!complete}
          onClick={submit}
        >
          {t("ask.submit")}
        </Button>
      </div>
    </div>
  )
}
