"use client"

import type {
  AgentDecisionTarget,
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
  const persistedTargets = buildPersistedTargetMap(events)
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
      const decision = parseWaitingDecision(event, persistedTargets)
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

export function parseWaitingDecision(
  event: AgentRuntimeEvent,
  persistedTargets: ReadonlyMap<string, AgentDecisionTarget | null> = new Map(),
): AgentWaitingDecision {
  const decision = parseRuntimeWaitingDecision(event)
  return {
    ...decision,
    target: persistedTargets.get(decision.actionId) ?? null,
  }
}

export function buildPersistedTargetMap(events: AgentRuntimeEvent[]) {
  const targets = new Map<string, AgentDecisionTarget | null>()
  for (const event of events) {
    if (event.type !== "action.risk_assessed") continue
    const actionId = String(event.payload.action_id || "")
    const target = parsePersistedTarget(event.payload.target)
    if (actionId) targets.set(actionId, target)
  }
  return targets
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

function parsePersistedTarget(target: unknown): AgentDecisionTarget | null {
  if (!target || typeof target !== "object" || Array.isArray(target)) return null
  const record = target as Record<string, unknown>
  const kind = String(record.kind || "")
  if (kind !== "local" && kind !== "remote_ssh" && kind !== "container") return null
  return {
    kind,
    trustDomain: stringOrNull(record.trust_domain),
    identity: stringOrNull(record.identity),
    connectionId: stringOrNull(record.connection_id),
  }
}

function stringOrNull(value: unknown) {
  return typeof value === "string" && value ? value : null
}
