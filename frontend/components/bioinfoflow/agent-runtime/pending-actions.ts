import type {
  AgentActionDecision,
  AgentAskUserQuestion,
  AgentRuntimeEvent,
  AgentWaitingDecision,
} from "@/lib/agent-runtime"

// Waiting-decision events whose action has not yet been completed, failed, or
// decided. Latest-first so the most recent prompt renders on top.
export function getPendingActions(events: AgentRuntimeEvent[]) {
  const resolved = new Set(
    events
      .filter((event) =>
        ["action.completed", "action.failed", "action.decision_recorded"].includes(
          event.type,
        ),
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

export function hasPendingRuntimeAction(events: AgentRuntimeEvent[]) {
  return getPendingActions(events).length > 0
}

// Stable key of the currently-pending action ids. Changes whenever a new
// approval arrives, so the workbench can re-surface the panel even after the
// user dismissed a previous decision.
export function pendingDecisionKey(events: AgentRuntimeEvent[]) {
  return getPendingActions(events)
    .map((event) => String(event.payload.action_id || ""))
    .join(",")
}

export type AgentDecisionCardState = "pending" | "approved" | "rejected" | "answered"

export type AgentDecisionCard = AgentWaitingDecision & {
  state: AgentDecisionCardState
}

export function getActionDecisionCards(events: AgentRuntimeEvent[]) {
  const decisions = new Map<string, AgentRuntimeEvent>()
  for (const event of events) {
    if (event.type !== "action.decision_recorded") continue
    const actionId = String(event.payload.action_id || "")
    if (actionId) decisions.set(actionId, event)
  }

  return events
    .filter((event) => event.type === "action.waiting_decision")
    .map((event): AgentDecisionCard | null => {
      const decision = parseWaitingDecision(event)
      if (!decision.actionId) return null
      const decisionEvent = decisions.get(decision.actionId)
      if (!decisionEvent) return { ...decision, state: "pending" }
      if (hasProgressAfterDecision(events, event, decisionEvent)) return null
      return { ...decision, state: decisionState(decisionEvent) }
    })
    .filter((card): card is AgentDecisionCard => Boolean(card))
    .reverse()
}

export function getActionDecisionCardsByTurn(events: AgentRuntimeEvent[]) {
  const byTurn = new Map<string, AgentDecisionCard[]>()
  for (const card of getActionDecisionCards(events)) {
    const event = events.find(
      (item) =>
        item.type === "action.waiting_decision" &&
        String(item.payload.action_id || "") === card.actionId,
    )
    const turnId = event?.turn_id ?? null
    if (!turnId) continue
    byTurn.set(turnId, [...(byTurn.get(turnId) ?? []), card])
  }
  return byTurn
}

export function parseWaitingDecision(event: AgentRuntimeEvent): AgentWaitingDecision {
  const payload = event.payload ?? {}
  const raw = payload.interaction as
    | { kind?: string; questions?: unknown; plan?: unknown }
    | undefined
  let interaction: AgentWaitingDecision["interaction"] = null
  if (raw?.kind === "user_input") {
    interaction = {
      kind: "user_input",
      questions: Array.isArray(raw.questions)
        ? (raw.questions as AgentAskUserQuestion[])
        : [],
    }
  } else if (raw?.kind === "plan_approval") {
    interaction = { kind: "plan_approval", plan: String(raw.plan ?? "") }
  }
  return {
    actionId: String(payload.action_id || ""),
    name: typeof payload.name === "string" ? payload.name : undefined,
    kind: typeof payload.kind === "string" ? payload.kind : undefined,
    riskLevel: typeof payload.risk_level === "string" ? payload.risk_level : undefined,
    toolCallId:
      typeof payload.tool_call_id === "string" ? payload.tool_call_id : null,
    inputPreview:
      typeof payload.input_preview === "string" ? payload.input_preview : null,
    interaction,
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

function decisionState(event: AgentRuntimeEvent): AgentDecisionCardState {
  const decision = String(event.payload.decision || "") as AgentActionDecision
  if (decision === "reject") return "rejected"
  if (decision === "answer") return "answered"
  return "approved"
}
