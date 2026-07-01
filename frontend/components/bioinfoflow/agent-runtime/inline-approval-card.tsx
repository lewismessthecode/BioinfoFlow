"use client"

import { AlertTriangle, Check, CheckCircle2, XCircle } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type { AgentAnswer, AgentAskUserQuestion, AgentRuntimeDecisionView } from "@/lib/agent-runtime"
import { AskUserDecisionCard } from "./ask-user-card"
import type { AgentDecisionHandler } from "./types"

export function InlineApprovalCard({
  decision,
  onDecision,
}: {
  decision: AgentRuntimeDecisionView
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  const isPending = decision.state === "pending"

  if (decision.interaction?.kind === "user_input") {
    return (
      <InlineAskUserCard
        actionId={decision.actionId}
        questions={decision.interaction.questions}
        answer={decision.answer}
        state={decision.state}
        onDecision={onDecision}
      />
    )
  }

  const isPlanApproval = decision.interaction?.kind === "plan_approval"

  if (!isPending && !isPlanApproval) {
    return (
      <div
        id={decision.scrollTargetId}
        className="grid gap-1.5 text-xs text-muted-foreground"
        data-testid="inline-approval-summary"
      >
        <div className="flex min-h-6 items-center gap-2">
          <DecisionStateIcon state={decision.state} className="h-3.5 w-3.5" />
          <span className="min-w-0 flex-1 truncate">
            {t(`approval.state.${decision.state}`)}
          </span>
          {decision.riskLevel ? (
            <span className="shrink-0 text-[10px] uppercase tracking-wide text-muted-foreground/75">
              {decision.riskLevel}
            </span>
          ) : null}
        </div>
        <div className="grid gap-1 pl-5">
          <div className="font-mono text-foreground/65">
            {decision.name ?? decision.actionId}
          </div>
          {decision.inputPreview ? (
            <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words font-mono text-[11px] leading-5 text-foreground/60">
              {decision.inputPreview}
            </pre>
          ) : null}
        </div>
      </div>
    )
  }

  return (
    <div
      id={decision.scrollTargetId}
      className="mb-3 rounded-lg border border-border/55 bg-muted/[0.18] px-3 py-2.5 text-sm text-muted-foreground"
      data-testid={isPlanApproval ? "inline-plan-card" : "inline-approval-card"}
    >
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        {isPending ? <Check className="h-4 w-4" /> : <DecisionStateIcon state={decision.state} />}
        <span className="min-w-0 flex-1 font-medium text-foreground/65">
          {isPending
            ? isPlanApproval
              ? t("plan.reviewTitle")
              : t("sidecar.needsDecision")
            : t(`approval.state.${decision.state}`)}
        </span>
        {decision.riskLevel ? (
          <span className="rounded-full bg-muted px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
            {decision.riskLevel}
          </span>
        ) : null}
      </div>

      <div className="grid gap-1.5 text-xs text-muted-foreground">
        <div className="font-mono">{decision.name ?? decision.actionId}</div>
        {isPlanApproval ? (
          <pre className="max-h-52 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background/60 p-2 font-mono text-foreground/75">
            {decision.interaction?.kind === "plan_approval" ? decision.interaction.plan : ""}
          </pre>
        ) : decision.inputPreview ? (
          <pre className="max-h-32 overflow-auto whitespace-pre-wrap break-words rounded-md bg-background/60 p-2 font-mono text-foreground/75">
            {decision.inputPreview}
          </pre>
        ) : null}
      </div>

      {isPending && onDecision ? (
        <div className="mt-3 flex items-center gap-2">
          <Button
            type="button"
            size="sm"
            variant="secondary"
            className="h-8 rounded-full"
            onClick={() => onDecision(decision.actionId, "approve")}
          >
            <Check className="h-3.5 w-3.5" />
            {isPlanApproval ? t("plan.approveAndAct") : t("approve")}
          </Button>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="h-8 rounded-full bg-card"
            onClick={() => onDecision(decision.actionId, "reject")}
          >
            {isPlanApproval ? t("plan.keepPlanning") : t("reject")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function InlineAskUserCard({
  actionId,
  questions,
  answer,
  state,
  onDecision,
}: {
  actionId: string
  questions: AgentAskUserQuestion[]
  answer?: AgentAnswer | null
  state: AgentRuntimeDecisionView["state"]
  onDecision?: AgentDecisionHandler
}) {
  const t = useTranslations("agentRuntime")
  const readOnly = state !== "pending"
  return (
    <AskUserDecisionCard
      id={`agent-decision-${actionId}`}
      actionId={actionId}
      questions={questions}
      onDecision={onDecision}
      answer={answer}
      readOnly={readOnly}
      stateLabel={readOnly ? t(`approval.state.${state}`) : null}
      inline
      testId="inline-ask-user-card"
    />
  )
}

function DecisionStateIcon({
  state,
  className = "h-4 w-4",
}: {
  state: AgentRuntimeDecisionView["state"]
  className?: string
}) {
  const iconClassName = `${className} text-muted-foreground`
  if (state === "rejected") return <XCircle className={iconClassName} />
  if (state === "failed" || state === "cancelled") {
    return <AlertTriangle className={iconClassName} />
  }
  return <CheckCircle2 className={iconClassName} />
}
