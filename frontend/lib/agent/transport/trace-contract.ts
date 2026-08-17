import type { TraceJsonValue } from "../trace-model/types"

const TRACE_PROTOCOL = "bioinfoflow.agent.trace"
const TRACE_PROTOCOL_VERSION = 1

export type TraceTransportModel = {
  provider: string
  model: string
  display_name: string
}

export type TraceTransportTurn = {
  id: string
  run_id: string
  index: number
  status: string
  model: TraceTransportModel | null
  started_at: string | null
  completed_at: string | null
}

export type TraceTransportComposition = {
  category: string
  characters: number
  tokens: number | null
}

export type TraceTransportContextSnapshot = {
  id: string
  turn_id: string
  model_trace_id: string
  sequence: number
  through_sequence: number
  compacted: boolean
  input_tokens: number | null
  cached_input_tokens: number | null
  max_context_tokens: number | null
  composition: TraceTransportComposition[]
  created_at: string
}

export type TraceTransportEvent = {
  id: string
  turn_id: string | null
  category: string
  title: string
  summary: string
  status: string | null
  sequence: number
  has_detail: boolean
  created_at: string
}

export type AgentTraceTimelineContract = {
  protocol: typeof TRACE_PROTOCOL
  protocol_version: typeof TRACE_PROTOCOL_VERSION
  session: {
    id: string
    title: string | null
    status: string
    model: TraceTransportModel
    created_at: string
    updated_at: string
  }
  turns: TraceTransportTurn[]
  context_flow: TraceTransportContextSnapshot[]
  events: TraceTransportEvent[]
}

export type AgentTraceDetailContract = {
  protocol: typeof TRACE_PROTOCOL
  protocol_version: typeof TRACE_PROTOCOL_VERSION
  event_id: string
  summary: { [key: string]: TraceJsonValue }
  payload: TraceJsonValue
  result: TraceJsonValue
  schema: TraceJsonValue
  timing: {
    started_at: string | null
    completed_at: string | null
    duration_ms: number | null
  } | null
}

export type TraceContractError = {
  code: "invalid_payload" | "unsupported_protocol_version"
  message: string
}

export type TraceContractResult<T> =
  | { ok: true; value: T }
  | { ok: false; error: TraceContractError }

export function parseAgentTraceTimeline(
  input: unknown,
): TraceContractResult<AgentTraceTimelineContract> {
  const envelope = validateEnvelope(input)
  if (!envelope.ok) return envelope
  const value = input as Record<string, unknown>
  if (
    !isTraceSession(value.session) ||
    !Array.isArray(value.turns) ||
    !value.turns.every(isTraceTurn) ||
    !Array.isArray(value.context_flow) ||
    !value.context_flow.every(isContextSnapshot) ||
    !Array.isArray(value.events) ||
    !value.events.every(isTraceEvent)
  ) {
    return invalidPayload("Agent Trace timeline payload is invalid")
  }
  return { ok: true, value: input as AgentTraceTimelineContract }
}

export function parseAgentTraceDetail(
  input: unknown,
): TraceContractResult<AgentTraceDetailContract> {
  const envelope = validateEnvelope(input)
  if (!envelope.ok) return envelope
  const value = input as Record<string, unknown>
  if (
    typeof value.event_id !== "string" ||
    !isJsonObject(value.summary) ||
    !isJsonValue(value.payload) ||
    !isJsonValue(value.result) ||
    !isJsonValue(value.schema) ||
    !(value.timing === null || isTraceTiming(value.timing))
  ) {
    return invalidPayload("Agent Trace detail payload is invalid")
  }
  return { ok: true, value: input as AgentTraceDetailContract }
}

function validateEnvelope(
  input: unknown,
): TraceContractResult<Record<string, unknown>> {
  if (!isRecord(input) || input.protocol !== TRACE_PROTOCOL) {
    return invalidPayload("Agent Trace protocol is missing or invalid")
  }
  if (input.protocol_version !== TRACE_PROTOCOL_VERSION) {
    return {
      ok: false,
      error: {
        code: "unsupported_protocol_version",
        message: `Unsupported Agent Trace protocol version: ${String(input.protocol_version)}`,
      },
    }
  }
  return { ok: true, value: input }
}

function isTraceSession(value: unknown) {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "status", "created_at", "updated_at"]) &&
    (value.title === null || typeof value.title === "string") &&
    isTraceModel(value.model)
  )
}

function isTraceModel(value: unknown): value is TraceTransportModel {
  return (
    isRecord(value) &&
    hasStrings(value, ["provider", "model", "display_name"])
  )
}

function isTraceTurn(value: unknown): value is TraceTransportTurn {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "run_id", "status"]) &&
    isPositiveInteger(value.index) &&
    (value.model === null || isTraceModel(value.model)) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at)
  )
}

function isContextSnapshot(
  value: unknown,
): value is TraceTransportContextSnapshot {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "turn_id",
      "model_trace_id",
      "created_at",
    ]) &&
    isPositiveInteger(value.sequence) &&
    isNonNegativeInteger(value.through_sequence) &&
    typeof value.compacted === "boolean" &&
    isNullableNonNegativeNumber(value.input_tokens) &&
    isNullableNonNegativeNumber(value.cached_input_tokens) &&
    isNullablePositiveNumber(value.max_context_tokens) &&
    Array.isArray(value.composition) &&
    value.composition.every(isContextComposition)
  )
}

function isContextComposition(
  value: unknown,
): value is TraceTransportComposition {
  return (
    isRecord(value) &&
    typeof value.category === "string" &&
    isNonNegativeNumber(value.characters) &&
    isNullableNonNegativeNumber(value.tokens)
  )
}

function isTraceEvent(value: unknown): value is TraceTransportEvent {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "category",
      "title",
      "summary",
      "created_at",
    ]) &&
    isNullableString(value.turn_id) &&
    isNullableString(value.status) &&
    isPositiveInteger(value.sequence) &&
    typeof value.has_detail === "boolean"
  )
}

function isTraceTiming(value: unknown) {
  return (
    isRecord(value) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableNonNegativeNumber(value.duration_ms)
  )
}

function isJsonObject(value: unknown): value is { [key: string]: TraceJsonValue } {
  return isRecord(value) && Object.values(value).every(isJsonValue)
}

function isJsonValue(value: unknown): value is TraceJsonValue {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return true
  }
  if (Array.isArray(value)) return value.every(isJsonValue)
  return isJsonObject(value)
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value)
}

function hasStrings(value: Record<string, unknown>, keys: string[]) {
  return keys.every((key) => typeof value[key] === "string")
}

function isNullableString(value: unknown) {
  return value === null || typeof value === "string"
}

function isNonNegativeInteger(value: unknown) {
  return Number.isInteger(value) && (value as number) >= 0
}

function isPositiveInteger(value: unknown) {
  return Number.isInteger(value) && (value as number) >= 1
}

function isNonNegativeNumber(value: unknown) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0
}

function isNullableNonNegativeNumber(value: unknown) {
  return value === null || isNonNegativeNumber(value)
}

function isNullablePositiveNumber(value: unknown) {
  return (
    value === null ||
    (typeof value === "number" && isNonNegativeNumber(value) && value >= 1)
  )
}

function invalidPayload(message: string): TraceContractResult<never> {
  return { ok: false, error: { code: "invalid_payload", message } }
}
