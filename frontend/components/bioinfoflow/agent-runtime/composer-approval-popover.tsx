"use client"

import { useMemo } from "react"
import { ArrowUpRight } from "lucide-react"

import type { AgentRuntimeDecisionView, AgentRuntimeEvent } from "@/lib/agent-runtime"
import { getActionDecisionCards } from "./pending-actions"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler } from "./types"
import { useTranslations } from "next-intl"

export function ComposerApprovalPopover({
  events,
}: {
  events: AgentRuntimeEvent[]
  onDecision: AgentDecisionHandler
}) {
  const cards = useMemo(() => getActionDecisionCards(events), [events])
  const pending = cards.find((card) => card.state === "pending") ?? null
  const resuming = cards.filter((card) => card.state !== "pending")

  if (!cards.length) return null

  return (
    <div className="mb-3 grid gap-2" data-testid="composer-approval-popover">
      {pending ? <DecisionJumpPrompt decision={pending} /> : null}
      {resuming.map((decision) => (
        <InlineApprovalCard key={decision.actionId} decision={decision} />
      ))}
    </div>
  )
}

function DecisionJumpPrompt({ decision }: { decision: AgentRuntimeDecisionView }) {
  const t = useTranslations("agentRuntime")

  return (
    <button
      type="button"
      className="flex w-fit items-center gap-2 rounded-full border border-amber-500/30 bg-background/95 px-3 py-1.5 text-xs font-medium text-amber-900 shadow-sm transition-colors hover:bg-amber-500/10 dark:text-amber-200"
      data-testid="composer-decision-jump"
      onClick={() => {
        document
          .getElementById(decision.scrollTargetId)
          ?.scrollIntoView({ block: "center", behavior: "smooth" })
      }}
    >
      <span>{t("sidecar.needsDecision")}</span>
      <span className="text-muted-foreground">·</span>
      <span>{t("approval.jumpToDecision")}</span>
      <ArrowUpRight className="h-3.5 w-3.5" />
    </button>
  )
}
