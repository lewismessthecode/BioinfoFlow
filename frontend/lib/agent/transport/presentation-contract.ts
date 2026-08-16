import type { AgentEvent, SessionSnapshot } from "../contracts"

const PRESENTATION_PROTOCOL_VERSION = 1 as const
const PRESENTATION_PROTOCOL = "bioinfoflow.agent.presentation" as const

export type PresentationDiagnosticCode =
  | "event_gap"
  | "invalid_payload"
  | "unknown_event_type"
  | "unsupported_protocol_version"

export type PresentationDiagnostic = {
  code: PresentationDiagnosticCode
  message: string
  originalType: string
  params: Record<string, string | number>
}

export type TransportParseResult<T> =
  | { ok: true; value: T }
  | { ok: false; diagnostic: PresentationDiagnostic }

export type ValidatedSnapshot = {
  protocolVersion: number
  snapshot: SessionSnapshot
  diagnostics: PresentationDiagnostic[]
}

export type ValidatedEvent = {
  protocolVersion: typeof PRESENTATION_PROTOCOL_VERSION
  event: AgentEvent
}

class PresentationContractError extends Error {
  readonly diagnostic: PresentationDiagnostic

  constructor(diagnostic: PresentationDiagnostic) {
    super(diagnostic.message)
    this.name = "PresentationContractError"
    this.diagnostic = diagnostic
  }
}

export function requirePresentationSnapshot(input: unknown): SessionSnapshot {
  const parsed = parsePresentationSnapshot(input)
  if (!parsed.ok) throw new PresentationContractError(parsed.diagnostic)
  return parsed.value.snapshot
}

const KNOWN_EVENT_TYPES = new Set([
  "snapshot",
  "run.updated",
  "assistant.delta",
  "tool.updated",
  "interaction.requested",
  "entry.committed",
])

export function parsePresentationSnapshot(
  input: unknown,
): TransportParseResult<ValidatedSnapshot> {
  const envelope = isRecord(input) && "snapshot" in input ? input : null
  const contract = readProtocolEnvelope(envelope ?? input)
  if (!contract.ok) return contract
  const snapshot = envelope ? envelope.snapshot : input
  if (!isSessionSnapshot(snapshot)) {
    return invalidPayload("snapshot")
  }
  const version = contract.version
  const diagnostics =
    version === PRESENTATION_PROTOCOL_VERSION
      ? []
      : [unsupportedVersionDiagnostic(version, "snapshot")]
  return {
    ok: true,
    value: {
      protocolVersion: isNonNegativeInteger(version)
        ? version
        : PRESENTATION_PROTOCOL_VERSION,
      snapshot,
      diagnostics,
    },
  }
}

export function parsePresentationEvent(
  input: unknown,
): TransportParseResult<ValidatedEvent> {
  if (!isRecord(input)) return invalidPayload("unknown")
  const originalType = typeof input.type === "string" ? input.type : "unknown"
  const contract = readProtocolEnvelope(input)
  if (!contract.ok) return contract
  const version = contract.version
  if (version !== PRESENTATION_PROTOCOL_VERSION) {
    return unsupportedVersion(version, originalType)
  }
  if (!KNOWN_EVENT_TYPES.has(originalType)) {
    return {
      ok: false,
      diagnostic: {
        code: "unknown_event_type",
        message: `Unsupported Agent presentation event: ${originalType}`,
        originalType,
        params: { originalType },
      },
    }
  }
  if (!isAgentEvent(input, originalType)) return invalidPayload(originalType)
  return {
    ok: true,
    value: {
      protocolVersion: PRESENTATION_PROTOCOL_VERSION,
      event: input,
    },
  }
}

function isAgentEvent(value: Record<string, unknown>, type: string): value is AgentEvent {
  switch (type) {
    case "snapshot":
      return isSessionSnapshot(value.snapshot)
    case "run.updated":
      return isRun(value.run)
    case "assistant.delta":
      return (
        hasStrings(value, ["run_id", "draft_id", "part_id", "delta"]) &&
        (value.part_type === "text" ||
          value.part_type === "reasoning_summary" ||
          value.part_type === "reasoning_trace") &&
        isNonNegativeInteger(value.start_offset) &&
        isNonNegativeInteger(value.end_offset)
      )
    case "tool.updated":
      return typeof value.run_id === "string" && isToolProgress(value.tool)
    case "interaction.requested":
      return (
        typeof value.run_id === "string" && isPendingInteraction(value.interaction)
      )
    case "entry.committed":
      return isHistoryEntry(value.entry)
    default:
      return false
  }
}

function isSessionSnapshot(value: unknown): value is SessionSnapshot {
  if (!isRecord(value) || !isRecord(value.session)) return false
  return (
    hasStrings(value.session, [
      "id",
      "user_id",
      "workspace_id",
      "status",
      "created_at",
      "updated_at",
    ]) &&
    isRecord(value.session.model) &&
    hasStrings(value.session.model, ["provider", "model", "display_name"]) &&
    typeof value.session.permission_mode === "string" &&
    typeof value.session.workspace_access === "string" &&
    Array.isArray(value.runs) &&
    value.runs.every(isRun) &&
    Array.isArray(value.entries) &&
    value.entries.every(isHistoryEntry) &&
    (value.active_run === null || isActiveRun(value.active_run))
  )
}

function isRun(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "session_id",
      "status",
      "created_at",
      "updated_at",
    ]) &&
    isNonNegativeInteger(value.revision)
  )
}

function isHistoryEntry(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasStrings(value, ["id", "session_id", "type", "created_at"]) ||
    !isNonNegativeInteger(value.sequence) ||
    !isNonNegativeInteger(value.schema_version) ||
    !isRecord(value.payload)
  ) {
    return false
  }
  switch (value.type) {
    case "message":
      return (
        ["user", "assistant", "tool"].includes(String(value.payload.role)) &&
        Array.isArray(value.payload.parts) &&
        value.payload.parts.every(
          (part) => isRecord(part) && hasStrings(part, ["id", "type"]),
        )
      )
    case "interaction_request":
      return (
        typeof value.payload.interaction_id === "string" &&
        isRecord(value.payload.request) &&
        typeof value.payload.request.type === "string"
      )
    case "interaction_response":
      return (
        typeof value.payload.interaction_id === "string" &&
        isRecord(value.payload.response) &&
        typeof value.payload.response.type === "string"
      )
    case "notice":
      return hasStrings(value.payload, ["code", "message"])
    case "plan":
      return (
        typeof value.payload.plan_id === "string" &&
        isNonNegativeInteger(value.payload.revision) &&
        Array.isArray(value.payload.items)
      )
    default:
      return true
  }
}

function isActiveRun(value: unknown): boolean {
  return (
    isRecord(value) &&
    isRun(value.run) &&
    (value.assistant_draft === null || isAssistantDraft(value.assistant_draft)) &&
    Array.isArray(value.tool_progress) &&
    value.tool_progress.every(isToolProgress) &&
    (value.pending_interaction === null ||
      isPendingInteraction(value.pending_interaction))
  )
}

function isAssistantDraft(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "run_id"]) &&
    Array.isArray(value.parts) &&
    value.parts.every(
      (part) =>
        isRecord(part) &&
        hasStrings(part, ["id", "type", "text"]) &&
        isNonNegativeInteger(part.end_offset),
    )
  )
}

function isToolProgress(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "call_id",
      "group_id",
      "execution_mode",
      "name",
      "display_name",
      "category",
      "summary",
      "status",
    ]) &&
    isNonNegativeInteger(value.revision)
  )
}

function isPendingInteraction(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["interaction_id", "run_id"]) &&
    isNonNegativeInteger(value.revision) &&
    isRecord(value.request) &&
    typeof value.request.type === "string"
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function readProtocolEnvelope(
  value: unknown,
):
  | { ok: true; version: unknown }
  | { ok: false; diagnostic: PresentationDiagnostic } {
  if (!isRecord(value)) {
    return { ok: true, version: PRESENTATION_PROTOCOL_VERSION }
  }
  if (
    "presentation_protocol" in value &&
    value.presentation_protocol !== PRESENTATION_PROTOCOL
  ) {
    return {
      ok: false,
      diagnostic: {
        code: "unsupported_protocol_version",
        message: `Unsupported Agent presentation protocol: ${String(value.presentation_protocol)}`,
        originalType: typeof value.type === "string" ? value.type : "snapshot",
        params: { version: String(value.presentation_protocol) },
      },
    }
  }
  return {
    ok: true,
    version:
      value.presentation_schema_version ??
      value.protocol_version ??
      PRESENTATION_PROTOCOL_VERSION,
  }
}

function hasStrings(
  value: Record<string, unknown>,
  keys: readonly string[],
): boolean {
  return keys.every((key) => typeof value[key] === "string")
}

function isNonNegativeInteger(value: unknown): value is number {
  return Number.isInteger(value) && Number(value) >= 0
}

function invalidPayload<T>(originalType: string): TransportParseResult<T> {
  return {
    ok: false,
    diagnostic: {
      code: "invalid_payload",
      message: `Invalid Agent presentation payload: ${originalType}`,
      originalType,
      params: { originalType },
    },
  }
}

function unsupportedVersion<T>(
  version: unknown,
  originalType: string,
): TransportParseResult<T> {
  return {
    ok: false,
    diagnostic: unsupportedVersionDiagnostic(version, originalType),
  }
}

function unsupportedVersionDiagnostic(
  version: unknown,
  originalType: string,
): PresentationDiagnostic {
  return {
    code: "unsupported_protocol_version",
    message: `Unsupported Agent presentation protocol version: ${String(version)}`,
    originalType,
    params: { version: String(version) },
  }
}
