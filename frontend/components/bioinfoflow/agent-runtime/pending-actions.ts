"use client"

import type {
  AgentRuntimeDecisionState,
  AgentRuntimeDecisionView,
  AgentRuntimeEvent,
  AgentWaitingDecision,
} from "@/lib/agent-runtime"
import {
  decisionScrollTargetId,
  parseRuntimeWaitingDecision,
} from "@/lib/agent-runtime"

export function getPendingActions(events: AgentRuntimeEvent[]) {
  const resolved = new Set(
    events
      .filter((event) =>
        [
          "action.completed",
          "action.failed",
          "action.cancelled",
          "action.decision_recorded",
        ].includes(event.type),
      )
      .map((event) => String(event.payload.action_id || "")),
  )
  return events
    .filter((event) => event.type === "action.waiting_decision")
    .filter((event) => {
      const actionId = String(event.payload.action_id || "")
      return actionId && !resolved.has(actionId)
    })
}

type AgentDecisionCard = AgentRuntimeDecisionView

export function getActionDecisionCards(events: AgentRuntimeEvent[]) {
  const decisions = new Map<string, AgentRuntimeEvent>()
  const resolvedWithoutDecision = new Map<string, AgentRuntimeEvent>()
  for (const event of events) {
    const actionId = String(event.payload.action_id || "")
    if (!actionId) continue
    if (event.type === "action.decision_recorded") {
      decisions.set(actionId, event)
      continue
    }
    if (["action.completed", "action.failed", "action.cancelled"].includes(event.type)) {
      resolvedWithoutDecision.set(actionId, event)
    }
  }

  return events
    .filter((event) => event.type === "action.waiting_decision")
    .map((event): AgentDecisionCard | null => {
      const decision = parseWaitingDecision(event)
      if (!decision.actionId) return null
      const resolver = resolvedWithoutDecision.get(decision.actionId)
      if (resolver && !decisions.has(decision.actionId)) return null
      const decisionEvent = decisions.get(decision.actionId)
      if (!decisionEvent) return decisionCardFromEvent(event, decision, "pending", event.seq)
      if (hasProgressAfterDecision(events, event, decisionEvent)) return null
      return decisionCardFromEvent(
        event,
        decision,
        decisionState(decisionEvent),
        decisionEvent.seq,
      )
    })
    .filter((card): card is AgentDecisionCard => Boolean(card))
    .reverse()
}

export function parseWaitingDecision(event: AgentRuntimeEvent): AgentWaitingDecision {
  return parseRuntimeWaitingDecision(event)
}

function decisionCardFromEvent(
  event: AgentRuntimeEvent,
  decision: AgentWaitingDecision,
  state: AgentRuntimeDecisionState,
  seqEnd: number,
): AgentDecisionCard {
  return {
    ...decision,
    state,
    turnId: event.turn_id ?? "",
    seqStart: event.seq,
    seqEnd,
    scrollTargetId: decisionScrollTargetId(decision.actionId),
  }
}

function hasProgressAfterDecision(
  events: AgentRuntimeEvent[],
  waitingEvent: AgentRuntimeEvent,
  decisionEvent: AgentRuntimeEvent,
) {
  return events.some((event) => {
    if (event.seq <= decisionEvent.seq) return false
    if (event.turn_id !== waitingEvent.turn_id) return false
    if (event.type.startsWith("assistant.")) return true
    return [
      "action.requested",
      "action.started",
      "action.completed",
      "action.failed",
      "action.cancelled",
      "turn.completed",
      "turn.failed",
      "turn.no_progress",
      "turn.recovery.enqueued",
      "turn.recovery.failed",
    ].includes(event.type)
  })
}

function decisionState(event: AgentRuntimeEvent): AgentRuntimeDecisionState {
  const decision = String(event.payload.decision || "")
  if (decision === "reject") return "rejected"
  if (decision === "answer") return "answered"
  return "approved"
}
