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
    case "state.loaded":
      return {
        session: action.payload.session,
        turns: action.payload.turns,
        events: sortEvents(dedupeEvents(action.payload.events)),
        timeline: buildAgentRuntimeTimeline(
          action.payload.turns,
          sortEvents(dedupeEvents(action.payload.events)),
        ),
        status: hasRunningTurn(action.payload.turns) ? "running" : "idle",
        error: null,
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
      const turns = applyEventToTurns(state.turns, action.event)
      const events = sortEvents(dedupeEvents([...state.events, action.event]))
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
  if (!exists) return [...turns, turn]
  return turns.map((item) => (item.id === turn.id ? turn : item))
}

function dedupeEvents(events: AgentRuntimeEvent[]) {
  const byId = new Map<string, AgentRuntimeEvent>()
  for (const event of events) byId.set(event.id, event)
  return [...byId.values()]
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
    event.type === "artifact.created"
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
