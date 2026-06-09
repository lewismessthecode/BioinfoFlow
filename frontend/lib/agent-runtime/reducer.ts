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
      const events = sortEvents(dedupeEvents([...state.events, action.event]))
      return {
        ...state,
        events,
        timeline: buildAgentRuntimeTimeline(state.turns, events),
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

function hasRunningTurn(turns: AgentRuntimeTurn[]) {
  return turns.some((turn) => turn.status === "queued" || turn.status === "running")
}
