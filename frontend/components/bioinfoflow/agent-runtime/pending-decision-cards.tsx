"use client"

import { useMemo } from "react"
import { Check } from "@/lib/icons"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
import type {
  AgentAskUserQuestion,
  AgentRuntimeEvent,
  AgentWaitingDecision,
} from "@/lib/agent-runtime"
import { AskUserDecisionCard } from "./ask-user-card"
import { DecisionSubmissionFeedback, useDecisionSubmission } from "./decision-submission"
import { DecisionTargetBadge } from "./decision-target-badge"
import {
  buildPersistedTargetMap,
  getPendingActions,
  parseWaitingDecision,
} from "./pending-actions"
import type { AgentDecisionHandler } from "./types"

export function PendingDecisionCards({
  events,
  onDecision,
}: {
  events: AgentRuntimeEvent[]
  onDecision: AgentDecisionHandler
}) {
  const decisions = useMemo(
    () => {
      const persistedTargets = buildPersistedTargetMap(events)
      return getPendingActions(events).map((event) =>
        parseWaitingDecision(event, persistedTargets),
      )
    },
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
  const submission = useDecisionSubmission(decision.actionId, onDecision)
  return (
    <div className="rounded-[14px] border border-foreground/12 bg-foreground/[0.045] px-3 py-3 text-sm" data-testid="pending-approval-card">
      <div className="mb-1 font-medium text-foreground/82">
        {t("sidecar.needsDecision")}
      </div>
      <div className="mb-1 font-mono text-xs text-muted-foreground">
        {decision.name ?? decision.actionId}
        {decision.riskLevel ? (
          <span className="ml-2 rounded-md bg-muted px-1.5 py-0.5 text-foreground/65">
            {decision.riskLevel}
          </span>
        ) : null}
        <DecisionTargetBadge target={decision.target} />
      </div>
      {decision.inputPreview ? (
        <div className="mb-3 truncate font-mono text-xs text-muted-foreground/82">
          {decision.inputPreview}
        </div>
      ) : null}
      <div className="flex items-center gap-2">
        <Button
          type="button"
          size="sm"
          className="h-8 rounded-md"
          onClick={() => void submission.submit("approve")}
          disabled={submission.busy}
        >
          <Check className="h-3.5 w-3.5" />
          {t("approve")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 rounded-md bg-card"
          onClick={() => void submission.submit("reject")}
          disabled={submission.busy}
        >
          {t("reject")}
        </Button>
      </div>
      <DecisionSubmissionFeedback
        busy={submission.busy}
        error={submission.error}
        onRetry={() => void submission.retry()}
      />
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
  const submission = useDecisionSubmission(actionId, onDecision)
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
          onClick={() => void submission.submit("approve")}
          disabled={submission.busy}
        >
          <Check className="h-3.5 w-3.5" />
          {t("plan.approveAndAct")}
        </Button>
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="h-8 rounded-full bg-card"
          onClick={() => void submission.submit("reject")}
          disabled={submission.busy}
        >
          {t("plan.keepPlanning")}
        </Button>
      </div>
      <DecisionSubmissionFeedback
        busy={submission.busy}
        error={submission.error}
        onRetry={() => void submission.retry()}
      />
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
  return (
    <AskUserDecisionCard
      actionId={actionId}
      questions={questions}
      onDecision={onDecision}
      testId="ask-user-card"
    />
  )
}
