"use client"

import { Check, CheckCircle2, XCircle } from "lucide-react"
import { useTranslations } from "next-intl"

import { Button } from "@/components/ui/button"
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

function DecisionStateIcon({ state }: { state: AgentDecisionCard["state"] }) {
  if (state === "rejected") return <XCircle className="h-4 w-4" />
  return <CheckCircle2 className="h-4 w-4" />
}
