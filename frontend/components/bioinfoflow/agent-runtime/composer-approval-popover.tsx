"use client"

import { useMemo } from "react"

import type { AgentRuntimeEvent } from "@/lib/agent-runtime"
import { getActionDecisionCards } from "./pending-actions"
import { PendingDecisionCards } from "./pending-decision-cards"
import { InlineApprovalCard } from "./inline-approval-card"
import type { AgentDecisionHandler } from "./types"

export function ComposerApprovalPopover({
  events,
  onDecision,
}: {
  events: AgentRuntimeEvent[]
  onDecision: AgentDecisionHandler
}) {
  const cards = useMemo(() => getActionDecisionCards(events), [events])
  const resuming = cards.filter((card) => card.state !== "pending")
  const hasPending = cards.some((card) => card.state === "pending")

  if (!cards.length) return null

  return (
    <div className="mb-3 grid gap-2" data-testid="composer-approval-popover">
      {hasPending ? <PendingDecisionCards events={events} onDecision={onDecision} /> : null}
      {resuming.map((decision) => (
        <InlineApprovalCard key={decision.actionId} decision={decision} />
      ))}
    </div>
  )
}
