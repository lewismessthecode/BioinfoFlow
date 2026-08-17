import type {
  AgentTraceCategory,
  AgentTraceEvent,
  AgentTraceEventDetail,
  AgentTraceModel,
  AgentTracePhase,
  AgentTraceViewModel,
} from "../trace-model/types"
import {
  parseAgentTraceDetail,
  parseAgentTraceTimeline,
  type AgentTraceDetailContract,
  type AgentTraceTimelineContract,
  type TraceContractError,
  type TraceTransportEvent,
  type TraceTransportModel,
} from "../transport/trace-contract"

export type AgentTraceProjectionResult =
  | { ok: true; view: AgentTraceViewModel }
  | { ok: false; error: TraceContractError }

export type AgentTraceDetailProjectionResult =
  | { ok: true; detail: AgentTraceEventDetail }
  | { ok: false; error: TraceContractError }

export function createAgentTraceView(input: unknown): AgentTraceProjectionResult {
  const parsed = parseAgentTraceTimeline(input)
  if (!parsed.ok) return parsed
  return { ok: true, view: projectTimeline(parsed.value) }
}

export function createAgentTraceDetail(
  input: unknown,
): AgentTraceDetailProjectionResult {
  const parsed = parseAgentTraceDetail(input)
  if (!parsed.ok) return parsed
  return { ok: true, detail: projectDetail(parsed.value) }
}

function projectTimeline(
  timeline: AgentTraceTimelineContract,
): AgentTraceViewModel {
  const orderedEvents = timeline.events.toSorted(
    (left, right) => left.sequence - right.sequence,
  )
  const knownTurnIds = new Set(timeline.turns.map((turn) => turn.id))
  const eventsByTurn = new Map<string, TraceTransportEvent[]>()
  const preambleEvents: TraceTransportEvent[] = []
  for (const event of orderedEvents) {
    if (event.turn_id === null || !knownTurnIds.has(event.turn_id)) {
      preambleEvents.push(event)
      continue
    }
    const current = eventsByTurn.get(event.turn_id) ?? []
    current.push(event)
    eventsByTurn.set(event.turn_id, current)
  }

  const turns = timeline.turns
    .toSorted((left, right) => left.index - right.index)
    .map((turn) => {
      const events = eventsByTurn.get(turn.id) ?? []
      const finalAssistantId = [...events]
        .reverse()
        .find((event) => event.category === "assistant")?.id
      return {
        id: turn.id,
        runId: turn.run_id,
        index: turn.index,
        status: turn.status,
        model: turn.model ? projectModel(turn.model) : null,
        events: events.map((event) =>
          projectEvent(event, event.id === finalAssistantId),
        ),
      }
    })

  return {
    protocolVersion: timeline.protocol_version,
    session: {
      id: timeline.session.id,
      title: timeline.session.title,
      status: timeline.session.status,
      model: projectModel(timeline.session.model),
    },
    preambleEvents: preambleEvents.map((event) =>
      projectEvent(event, false),
    ),
    turns,
    contextFlow: timeline.context_flow
      .toSorted((left, right) => left.sequence - right.sequence)
      .map((snapshot) => ({
        id: snapshot.id,
        turnId: snapshot.turn_id,
        modelTraceId: snapshot.model_trace_id,
        sequence: snapshot.sequence,
        throughSequence: snapshot.through_sequence,
        compacted: snapshot.compacted,
        inputTokens: snapshot.input_tokens,
        cachedInputTokens: snapshot.cached_input_tokens,
        maxContextTokens: snapshot.max_context_tokens,
        composition: snapshot.composition.map((item) => ({
          category: knownCategory(item.category),
          characters: item.characters,
          tokens: item.tokens,
        })),
      })),
    eventCount: orderedEvents.length,
  }
}

function projectEvent(
  event: TraceTransportEvent,
  finalAssistant: boolean,
): AgentTraceEvent {
  const category = knownCategory(event.category)
  return {
    id: event.id,
    turnId: event.turn_id,
    category,
    title: event.title,
    summary: event.summary,
    firstLine: event.summary.split(/\r?\n/, 1)[0] ?? "",
    status: event.status,
    sequence: event.sequence,
    hasDetail: event.has_detail,
    createdAt: event.created_at,
    phase: phaseFor(category, finalAssistant),
  }
}

function phaseFor(
  category: AgentTraceCategory,
  finalAssistant: boolean,
): AgentTracePhase {
  if (category === "system" || category === "context") return "pre_call"
  if (category === "user") return "user_input"
  if (category === "assistant" && finalAssistant) return "final_response"
  return "agent_work"
}

function projectModel(model: TraceTransportModel): AgentTraceModel {
  return {
    provider: model.provider,
    model: model.model,
    displayName: model.display_name,
  }
}

function projectDetail(detail: AgentTraceDetailContract): AgentTraceEventDetail {
  return {
    protocolVersion: detail.protocol_version,
    eventId: detail.event_id,
    summary: detail.summary,
    payload: detail.payload,
    result: detail.result,
    schema: detail.schema,
    timing: detail.timing
      ? {
          startedAt: detail.timing.started_at,
          completedAt: detail.timing.completed_at,
          durationMs: detail.timing.duration_ms,
        }
      : null,
  }
}

function knownCategory(value: string): AgentTraceCategory {
  return ["system", "user", "context", "assistant", "tool"].includes(value)
    ? (value as AgentTraceCategory)
    : "unknown"
}
