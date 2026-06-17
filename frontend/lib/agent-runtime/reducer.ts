import type {
  AgentRuntimeEvent,
  AgentRuntimeSession,
  AgentRuntimeStatePayload,
  AgentRuntimeTimelineEntry,
  AgentRuntimeTurn,
} from "./types"
import { buildAgentRuntimeTimeline } from "./timeline"

export type AgentRuntimeViewState = {
  session: AgentRuntimeSession | null
  turns: AgentRuntimeTurn[]
  events: AgentRuntimeEvent[]
  timeline: AgentRuntimeTimelineEntry[]
  status: "idle" | "loading" | "running" | "error"
  error: string | null
}

export type AgentRuntimeAction =
  | { type: "loading" }
  | { type: "state.loaded"; payload: AgentRuntimeStatePayload }
  | { type: "session.loading"; session: AgentRuntimeSession | null }
  | { type: "session.selected"; session: AgentRuntimeSession | null }
  | { type: "turn.upsert"; turn: AgentRuntimeTurn }
  | { type: "event.append"; event: AgentRuntimeEvent }
  | { type: "error"; message: string }
  | { type: "idle" }

export const initialAgentRuntimeState: AgentRuntimeViewState = {
  session: null,
  turns: [],
  events: [],
  timeline: [],
  status: "idle",
  error: null,
}

export function agentRuntimeReducer(
  state: AgentRuntimeViewState,
  action: AgentRuntimeAction,
): AgentRuntimeViewState {
  switch (action.type) {
    case "loading":
      return { ...state, status: "loading", error: null }
    case "state.loaded": {
      const sameSession = state.session?.id === action.payload.session.id
      const turns = mergeTurns(sameSession ? state.turns : [], action.payload.turns)
      const events = sortEvents(
        dedupeEvents([...(sameSession ? state.events : []), ...action.payload.events]),
      )
      return {
        session: sameSession
          ? fresherSession(state.session, action.payload.session)
          : action.payload.session,
        turns,
        events,
        timeline: buildAgentRuntimeTimeline(turns, events),
        status: hasRunningTurn(turns) ? "running" : "idle",
        error: null,
      }
    }
    case "session.loading":
      return {
        ...initialAgentRuntimeState,
        session: action.session,
        status: "loading",
      }
    case "session.selected":
      return {
        ...initialAgentRuntimeState,
        session: action.session,
        status: action.session ? "loading" : "idle",
      }
    case "turn.upsert": {
      const turns = upsertTurn(state.turns, action.turn)
      return {
        ...state,
        turns,
        timeline: buildAgentRuntimeTimeline(turns, state.events),
        status: hasRunningTurn(turns) ? "running" : "idle",
        error: null,
      }
    }
    case "event.append": {
      const events = sortEvents(dedupeEvents([...state.events, action.event]))
      const turns = applyEventToTurns(state.turns, action.event)
      return {
        ...state,
        turns,
        events,
        timeline: buildAgentRuntimeTimeline(turns, events),
        status: hasRunningTurn(turns) ? "running" : "idle",
        error: null,
      }
    }
    case "error":
      return { ...state, status: "error", error: action.message }
    case "idle":
      return { ...state, status: "idle" }
  }
}

function upsertTurn(turns: AgentRuntimeTurn[], turn: AgentRuntimeTurn) {
  const exists = turns.some((item) => item.id === turn.id)
  if (!exists) return sortTurns([...turns, turn])
  return sortTurns(
    turns.map((item) => (item.id === turn.id ? fresherTurn(item, turn) : item)),
  )
}

function mergeTurns(existing: AgentRuntimeTurn[], incoming: AgentRuntimeTurn[]) {
  const byId = new Map<string, AgentRuntimeTurn>()
  for (const turn of existing) byId.set(turn.id, turn)
  for (const turn of incoming) {
    const previous = byId.get(turn.id)
    byId.set(turn.id, previous ? fresherTurn(previous, turn) : turn)
  }
  return sortTurns([...byId.values()])
}

function fresherTurn(existing: AgentRuntimeTurn, incoming: AgentRuntimeTurn) {
  const existingTime = timestamp(existing.updated_at)
  const incomingTime = timestamp(incoming.updated_at)
  if (incomingTime > existingTime) return incoming
  if (incomingTime < existingTime) return existing
  if (isTerminalTurn(incoming.status) && !isTerminalTurn(existing.status)) return incoming
  if (isTerminalTurn(existing.status) && !isTerminalTurn(incoming.status)) return existing
  return incoming
}

function fresherSession(
  existing: AgentRuntimeSession | null,
  incoming: AgentRuntimeSession,
) {
  if (!existing || existing.id !== incoming.id) return incoming
  return timestamp(incoming.updated_at) >= timestamp(existing.updated_at) ? incoming : existing
}

function isTerminalTurn(status: AgentRuntimeTurn["status"]) {
  return status === "completed" || status === "failed" || status === "cancelled"
}

function timestamp(value?: string | null) {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function sortTurns(turns: AgentRuntimeTurn[]) {
  return [...turns].sort((a, b) => timestamp(a.created_at) - timestamp(b.created_at))
}

function dedupeEvents(events: AgentRuntimeEvent[]) {
  const bySequence = new Map<string, AgentRuntimeEvent>()
  for (const event of events) bySequence.set(`${event.session_id}:${event.seq}`, event)
  return [...bySequence.values()]
}

function sortEvents(events: AgentRuntimeEvent[]) {
  return [...events].sort((a, b) => a.seq - b.seq)
}

function applyEventToTurns(turns: AgentRuntimeTurn[], event: AgentRuntimeEvent) {
  const turnId = event.turn_id ?? null
  if (!turnId) return turns

  const nextStatus = projectTurnStatusFromEvent(event)
  const shouldPromoteRunning =
    nextStatus === null && indicatesActiveTurnOutput(event)

  if (!nextStatus && !shouldPromoteRunning) {
    return turns
  }

  return turns.map((turn) => {
    if (turn.id !== turnId) return turn

    const status = nextStatus ?? promoteTurnStatusFromOutput(turn.status)
    if (status === turn.status && nextStatus !== "failed") {
      return turn
    }

    const nextTurn: AgentRuntimeTurn = {
      ...turn,
      status,
      updated_at: event.updated_at || turn.updated_at,
    }

    if (status === "running" && !turn.started_at) {
      nextTurn.started_at = event.created_at
    }

    if (
      (status === "completed" || status === "failed" || status === "cancelled") &&
      !turn.completed_at
    ) {
      nextTurn.completed_at = event.created_at
    }

    if (status === "failed") {
      nextTurn.error_message =
        typeof event.payload.error_message === "string"
          ? event.payload.error_message
          : turn.error_message
    }

    return nextTurn
  })
}

function projectTurnStatusFromEvent(
  event: AgentRuntimeEvent,
): AgentRuntimeTurn["status"] | null {
  switch (event.type) {
    case "turn.started":
      return "running"
    case "turn.completed":
      return "completed"
    case "turn.failed":
      return "failed"
    case "turn.cancelled":
    case "turn.interrupted":
      return "cancelled"
    case "action.waiting_decision":
      return "waiting_approval"
    default:
      return null
  }
}

function indicatesActiveTurnOutput(event: AgentRuntimeEvent) {
  return (
    event.type.startsWith("assistant.") ||
    event.type === "action.requested" ||
    event.type === "action.started" ||
    event.type === "action.completed" ||
    event.type === "action.failed" ||
    event.type === "action.cancelled" ||
    event.type === "action.decision_recorded" ||
    event.type === "artifact.created" ||
    event.type === "model.retrying" ||
    event.type === "model.fallback" ||
    event.type === "turn.no_progress" ||
    event.type === "turn.recovery.enqueued" ||
    event.type === "turn.recovery.failed"
  )
}

function promoteTurnStatusFromOutput(status: AgentRuntimeTurn["status"]) {
  if (
    status === "queued" ||
    status === "waiting_approval" ||
    status === "waiting_user"
  ) {
    return "running"
  }
  return status
}

function hasRunningTurn(turns: AgentRuntimeTurn[]) {
  return turns.some((turn) => turn.status === "queued" || turn.status === "running")
}
