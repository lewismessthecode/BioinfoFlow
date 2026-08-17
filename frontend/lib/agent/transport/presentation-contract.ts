import type {
  AgentEvent,
  HistoryEntry,
  MessagePart,
  PresentationEvent,
  PresentationSnapshot,
  SessionSnapshot,
} from "../contracts"

type ToolOutputContentMessagePart = Exclude<
  MessagePart,
  { type: "tool_call" } | { type: "tool_result" }
>

const PRESENTATION_PROTOCOL_VERSION = 1 as const
const PRESENTATION_PROTOCOL = "bioinfoflow.agent.presentation" as const

const TOOL_EXECUTION_MODES = new Set(["parallel", "serial", "mixed"])
const TOOL_CATEGORIES = new Set([
  "read",
  "search",
  "command",
  "edit",
  "write",
  "workflow",
  "plan",
  "interaction",
  "other",
])
const TOOL_PROGRESS_STATUSES = new Set([
  "pending",
  "running",
  "completed",
  "failed",
  "blocked",
  "cancelled",
  "interaction_required",
])
const PUBLIC_DETAIL_KINDS = new Set([
  "command",
  "working_directory",
  "path",
  "input",
  "output",
  "changes",
  "error",
  "metadata",
])
const PUBLIC_DETAIL_FORMATS = new Set([
  "text",
  "code",
  "path",
  "json",
  "diff",
])
const PERMISSION_MODES = new Set([
  "ask_changes",
  "ask_dangerous",
  "full_access",
])
const WORKSPACE_ACCESS_MODES = new Set(["read_only", "read_write"])
const SESSION_STATUSES = new Set([
  "active",
  "archived",
  "closing",
  "deleted",
])
const RUN_STATUSES = new Set([
  "queued",
  "running",
  "waiting_user",
  "completed",
  "failed",
  "cancelled",
])
const RUN_PHASES = new Set(["model", "tools", "interaction"])
const ENVIRONMENT_SCOPE_MODES = new Set(["auto", "manual"])
const ENVIRONMENT_KINDS = new Set(["local", "ssh"])
const MESSAGE_ROLES = new Set(["user", "assistant", "tool"])
const PLAN_ITEM_STATUSES = new Set(["pending", "in_progress", "completed"])
const KNOWN_HISTORY_ENTRY_TYPES = new Set([
  "message",
  "interaction_request",
  "interaction_response",
  "notice",
  "plan",
  "unknown",
])
const KNOWN_MESSAGE_PART_TYPES = new Set([
  "text",
  "reasoning_summary",
  "reasoning_trace",
  "attachment_ref",
  "file_ref",
  "directory_ref",
  "workflow_ref",
  "run_ref",
  "artifact_ref",
  "tool_call",
  "tool_result",
  "unknown",
])

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
  snapshot: PresentationSnapshot
  diagnostics: PresentationDiagnostic[]
}

export type ValidatedEvent = {
  protocolVersion: typeof PRESENTATION_PROTOCOL_VERSION
  event: PresentationEvent
}

class PresentationContractError extends Error {
  readonly diagnostic: PresentationDiagnostic

  constructor(diagnostic: PresentationDiagnostic) {
    super(diagnostic.message)
    this.name = "PresentationContractError"
    this.diagnostic = diagnostic
  }
}

export function requirePresentationSnapshot(input: unknown): PresentationSnapshot {
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
  const snapshotInput = envelope ? envelope.snapshot : input
  if (!isSessionSnapshot(snapshotInput)) {
    return invalidPayload("snapshot")
  }
  const version = contract.version
  const protocolVersion = isNonNegativeInteger(version)
    ? version
    : PRESENTATION_PROTOCOL_VERSION
  const diagnostics =
    version === PRESENTATION_PROTOCOL_VERSION
      ? []
      : [unsupportedVersionDiagnostic(version, "snapshot")]
  return {
    ok: true,
    value: {
      protocolVersion,
      snapshot: normalizePresentationSnapshot(snapshotInput, protocolVersion),
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
      event: normalizePresentationEvent(input),
    },
  }
}

function isAgentEvent(
  value: Record<string, unknown>,
  type: string,
): value is AgentEvent {
  switch (type) {
    case "snapshot":
      return isSessionSnapshot(value.snapshot)
    case "run.updated":
      return isRun(value.run)
    case "assistant.delta":
      if (
        !(
          hasStrings(value, ["run_id", "draft_id", "part_id", "delta"]) &&
          (value.part_type === "text" ||
            value.part_type === "reasoning_summary" ||
            value.part_type === "reasoning_trace") &&
          isNonNegativeInteger(value.start_offset) &&
          isNonNegativeInteger(value.end_offset)
        )
      ) {
        return false
      }
      return value.part_type === "reasoning_trace"
        ? isRequiredReasoningMetadata(value)
        : isOptionalReasoningMetadata(value)
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
  return (
    isRecord(value) &&
    isSessionView(value.session) &&
    Array.isArray(value.runs) &&
    value.runs.every(isRun) &&
    Array.isArray(value.entries) &&
    value.entries.every(isHistoryEntry) &&
    (value.active_run === null || isActiveRun(value.active_run))
  )
}

function isSessionView(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "id",
      "user_id",
      "workspace_id",
      "created_at",
      "updated_at",
    ]) &&
    isNullableString(value.project_id) &&
    isNullableString(value.title) &&
    isModelSummary(value.model) &&
    isKnownString(value.permission_mode, PERMISSION_MODES) &&
    isKnownString(value.workspace_access, WORKSPACE_ACCESS_MODES) &&
    (value.settings_revision === undefined ||
      isPositiveInteger(value.settings_revision)) &&
    (value.environment_scope === undefined ||
      isConversationEnvironmentScope(value.environment_scope)) &&
    isKnownString(value.status, SESSION_STATUSES)
  )
}

function isRun(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "session_id", "created_at", "updated_at"]) &&
    isKnownString(value.status, RUN_STATUSES) &&
    (value.phase === null || isKnownString(value.phase, RUN_PHASES)) &&
    isNonNegativeInteger(value.revision) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableString(value.termination_reason) &&
    (value.error === null || isRunError(value.error)) &&
    (value.execution_config === null ||
      value.execution_config === undefined ||
      isRunExecutionConfig(value.execution_config))
  )
}

function isModelSummary(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["provider", "model", "display_name"]) &&
    typeof value.supports_vision === "boolean" &&
    typeof value.supports_reasoning === "boolean" &&
    typeof value.supports_tools === "boolean"
  )
}

function isRunError(value: unknown): boolean {
  return isRecord(value) && hasStrings(value, ["code", "message"])
}

function isConversationEnvironmentScope(value: unknown): boolean {
  if (!isRecord(value) || !isKnownString(value.mode, ENVIRONMENT_SCOPE_MODES)) {
    return false
  }
  return value.mode === "auto"
    ? value.environment_ids === null
    : isStringArray(value.environment_ids) && value.environment_ids.length > 0
}

function isRunExecutionConfig(value: unknown): boolean {
  return (
    isRecord(value) &&
    isPositiveInteger(value.settings_revision) &&
    isModelSummary(value.model) &&
    isKnownString(value.permission_mode, PERMISSION_MODES) &&
    isKnownString(value.workspace_access, WORKSPACE_ACCESS_MODES) &&
    isRecord(value.environment_scope) &&
    isKnownString(value.environment_scope.mode, ENVIRONMENT_SCOPE_MODES) &&
    Array.isArray(value.environment_scope.environment_ids) &&
    value.environment_scope.environment_ids.every(
      (environmentId) => typeof environmentId === "string",
    ) &&
    Array.isArray(value.environment_targets) &&
    value.environment_targets.every(
      (target) =>
        isRecord(target) &&
        hasStrings(target, ["environment_id", "display_name"]) &&
        isKnownString(target.kind, ENVIRONMENT_KINDS) &&
        isNullableString(target.host),
    )
  )
}

function isHistoryEntry(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasStrings(value, ["id", "session_id", "type", "created_at"]) ||
    !isNullableString(value.run_id) ||
    !isPositiveInteger(value.sequence) ||
    !isPositiveInteger(value.schema_version) ||
    !isRecord(value.payload)
  ) {
    return false
  }
  switch (value.type) {
    case "message":
      return (
        isKnownString(value.payload.role, MESSAGE_ROLES) &&
        Array.isArray(value.payload.parts) &&
        value.payload.parts.every(isMessagePart)
      )
    case "interaction_request":
      return (
        typeof value.payload.interaction_id === "string" &&
        isInteractionRequest(value.payload.request)
      )
    case "interaction_response":
      return (
        typeof value.payload.interaction_id === "string" &&
        isInteractionResponse(value.payload.response)
      )
    case "notice":
      return (
        hasStrings(value.payload, ["code", "message"]) &&
        (value.payload.params === undefined || isRecord(value.payload.params)) &&
        (value.payload.details === null || isRecord(value.payload.details))
      )
    case "plan":
      return (
        typeof value.payload.plan_id === "string" &&
        isPositiveInteger(value.payload.revision) &&
        isOptionalNullableString(value.payload.title) &&
        Array.isArray(value.payload.items) &&
        value.payload.items.every(isPlanItem) &&
        typeof value.payload.updated_at === "string"
      )
    case "unknown":
      return hasStrings(value.payload, ["original_type", "display_text"])
    default:
      return true
  }
}

function isPlanItem(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "text"]) &&
    isKnownString(value.status, PLAN_ITEM_STATUSES)
  )
}

function isMessagePart(value: unknown): boolean {
  if (!isRecord(value) || !hasStrings(value, ["id", "type"])) return false
  switch (value.type) {
    case "text":
    case "reasoning_summary":
      return typeof value.text === "string"
    case "reasoning_trace":
      return (
        typeof value.text === "string" && isRequiredReasoningMetadata(value)
      )
    case "attachment_ref":
      return (
        hasStrings(value, ["attachment_id", "filename", "kind"]) &&
        isNullableString(value.mime_type) &&
        isNonNegativeInteger(value.size_bytes)
      )
    case "file_ref":
    case "directory_ref":
      return (
        typeof value.label === "string" &&
        isOptionalNullableString(value.project_id) &&
        isOptionalNullableString(value.attachment_id) &&
        isOptionalNullableString(value.path)
      )
    case "workflow_ref":
      return (
        hasStrings(value, ["workflow_id", "label"]) &&
        isOptionalNullableString(value.project_id)
      )
    case "run_ref":
      return hasStrings(value, ["run_id", "label"])
    case "artifact_ref":
      return (
        typeof value.artifact_id === "string" &&
        isNullableString(value.title) &&
        isNullableString(value.media_type)
      )
    case "tool_call":
      return (
        hasStrings(value, [
          "call_id",
          "group_id",
          "execution_mode",
          "name",
          "display_name",
          "category",
          "summary",
        ]) &&
        isKnownString(value.execution_mode, TOOL_EXECUTION_MODES) &&
        isKnownString(value.category, TOOL_CATEGORIES) &&
        isRecord(value.arguments) &&
        isOptionalPublicDetails(value.public_details)
      )
    case "tool_result":
      return (
        hasStrings(value, ["call_id", "status"]) &&
        isKnownString(value.status, TOOL_PROGRESS_STATUSES) &&
        isNullableString(value.summary) &&
        (value.output === null || isToolOutput(value.output)) &&
        isNullableString(value.started_at) &&
        isNullableString(value.completed_at) &&
        isNullableString(value.error) &&
        isOptionalPublicDetails(value.public_details)
      )
    case "unknown":
      return hasStrings(value, ["original_type", "display_text"])
    default:
      return true
  }
}

function isOptionalPublicDetails(value: unknown): boolean {
  return value === undefined || (Array.isArray(value) && value.every(isPublicDetail))
}

function isPublicDetail(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "kind", "value", "format"]) &&
    isKnownString(value.kind, PUBLIC_DETAIL_KINDS) &&
    isKnownString(value.format, PUBLIC_DETAIL_FORMATS) &&
    isNullableString(value.label) &&
    typeof value.copyable === "boolean" &&
    typeof value.truncated === "boolean" &&
    typeof value.redacted === "boolean"
  )
}

function isToolOutput(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false
  switch (value.type) {
    case "text":
      return typeof value.text === "string"
    case "json":
      return "value" in value && isJsonValue(value.value)
    case "content_parts":
      return (
        Array.isArray(value.parts) &&
        value.parts.every(
          (part) =>
            isMessagePart(part) &&
            isRecord(part) &&
            part.type !== "tool_call" &&
            part.type !== "tool_result",
        )
      )
    default:
      return false
  }
}

function isInteractionRequest(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false
  switch (value.type) {
    case "approval":
      return (
        hasStrings(value, ["call_id", "tool_name", "summary"]) &&
        isNullableString(value.input_preview) &&
        Array.isArray(value.allowed_responses) &&
        value.allowed_responses.length > 0 &&
        value.allowed_responses.every(
          (response) => response === "approve" || response === "reject",
        ) &&
        (value.target === undefined || isApprovalTarget(value.target)) &&
        isApprovalRisk(value.risk)
      )
    case "ask_user":
      return (
        typeof value.call_id === "string" &&
        Array.isArray(value.questions) &&
        value.questions.length > 0 &&
        value.questions.every(isAskUserQuestion)
      )
    case "recovery":
      return (
        hasStrings(value, ["call_id", "tool_name", "message"]) &&
        isOptionalNullableString(value.message_code) &&
        (value.message_params === undefined || isRecord(value.message_params)) &&
        Array.isArray(value.options) &&
        value.options.every(isInteractionOption)
      )
    default:
      return false
  }
}

function isInteractionResponse(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false
  switch (value.type) {
    case "approval":
      return typeof value.approved === "boolean"
    case "ask_user":
      return isRecord(value.answers) && Object.values(value.answers).every(isJsonValue)
    case "recovery":
      return (
        value.choice === "inspect" ||
        value.choice === "retry" ||
        value.choice === "cancel"
      )
    default:
      return false
  }
}

function isApprovalTarget(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["environment_id", "display_name", "kind"]) &&
    (value.kind === "local" || value.kind === "ssh") &&
    isOptionalNullableString(value.host)
  )
}

function isApprovalRisk(value: unknown): boolean {
  return (
    isRecord(value) &&
    typeof value.level === "string" &&
    isStringArray(value.effects) &&
    isStringArray(value.reasons) &&
    (value.reason_codes === undefined || isStringArray(value.reason_codes)) &&
    isOptionalNullableString(value.justification) &&
    isStringArray(value.affected_resources)
  )
}

function isAskUserQuestion(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "header", "question"]) &&
    typeof value.multi_select === "boolean" &&
    Array.isArray(value.options) &&
    value.options.length >= 2 &&
    value.options.length <= 3 &&
    value.options.every(isInteractionOption)
  )
}

function isInteractionOption(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["id", "label", "description"]) &&
    typeof value.recommended === "boolean"
  )
}

function isJsonValue(value: unknown): boolean {
  if (
    value === null ||
    typeof value === "string" ||
    typeof value === "boolean" ||
    (typeof value === "number" && Number.isFinite(value))
  ) {
    return true
  }
  if (Array.isArray(value)) return value.every(isJsonValue)
  return isRecord(value) && Object.values(value).every(isJsonValue)
}

function isRequiredReasoningMetadata(
  value: Record<string, unknown>,
): boolean {
  return (
    hasStrings(value, ["provider", "model", "source"]) &&
    typeof value.truncated === "boolean" &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at)
  )
}

function isOptionalReasoningMetadata(
  value: Record<string, unknown>,
): boolean {
  return (
    isOptionalNullableString(value.provider) &&
    isOptionalNullableString(value.model) &&
    isOptionalNullableString(value.source) &&
    (value.truncated === undefined || typeof value.truncated === "boolean") &&
    isOptionalNullableString(value.started_at) &&
    isOptionalNullableString(value.completed_at)
  )
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
    value.parts.every(isAssistantDraftPart)
  )
}

function isAssistantDraftPart(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasStrings(value, ["id", "type", "text"]) ||
    (value.type !== "text" &&
      value.type !== "reasoning_summary" &&
      value.type !== "reasoning_trace") ||
    !isNonNegativeInteger(value.end_offset)
  ) {
    return false
  }
  return value.type === "reasoning_trace"
    ? isRequiredReasoningMetadata(value)
    : isOptionalReasoningMetadata(value)
}

function isToolProgress(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, [
      "call_id",
      "group_id",
      "name",
      "display_name",
      "summary",
    ]) &&
    isKnownString(value.execution_mode, TOOL_EXECUTION_MODES) &&
    isKnownString(value.category, TOOL_CATEGORIES) &&
    isRecord(value.arguments) &&
    isKnownString(value.status, TOOL_PROGRESS_STATUSES) &&
    isNonNegativeInteger(value.revision) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableString(value.input_summary) &&
    isNullableString(value.output_summary) &&
    isNullableString(value.error) &&
    isOptionalPublicDetails(value.public_details)
  )
}

function isPendingInteraction(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, ["interaction_id", "run_id"]) &&
    isPositiveInteger(value.revision) &&
    isInteractionRequest(value.request)
  )
}

function normalizePresentationSnapshot(
  snapshot: SessionSnapshot,
  protocolVersion: number,
): PresentationSnapshot {
  const entries = snapshot.entries.map(normalizeHistoryEntry)
  const envelope = snapshot as unknown as Record<string, unknown>
  if (
    envelope.presentation_protocol === PRESENTATION_PROTOCOL &&
    envelope.presentation_schema_version === protocolVersion &&
    entries.every((entry, index) => entry === snapshot.entries[index])
  ) {
    return snapshot as PresentationSnapshot
  }
  return {
    ...snapshot,
    entries,
    presentation_protocol: PRESENTATION_PROTOCOL,
    presentation_schema_version: protocolVersion,
  }
}

function normalizePresentationEvent(event: AgentEvent): PresentationEvent {
  const normalized = (() => {
    switch (event.type) {
      case "snapshot":
        return {
          ...event,
          snapshot: normalizePresentationSnapshot(
            event.snapshot,
            PRESENTATION_PROTOCOL_VERSION,
          ),
        }
      case "entry.committed":
        return { ...event, entry: normalizeHistoryEntry(event.entry) }
      default:
        return event
    }
  })()
  return {
    ...normalized,
    presentation_protocol: PRESENTATION_PROTOCOL,
    presentation_schema_version: PRESENTATION_PROTOCOL_VERSION,
  } as PresentationEvent
}

function normalizeHistoryEntry(entry: HistoryEntry): HistoryEntry {
  const value = entry as unknown as Record<string, unknown>
  const payload = value.payload as Record<string, unknown>
  if (!KNOWN_HISTORY_ENTRY_TYPES.has(String(value.type)) || value.type === "unknown") {
    const originalType =
      value.type === "unknown" && typeof payload.original_type === "string"
        ? payload.original_type
        : String(value.type)
    const displayText =
      value.type === "unknown" && typeof payload.display_text === "string"
        ? payload.display_text
        : "Unsupported conversation activity"
    return {
      id: value.id as string,
      session_id: value.session_id as string,
      run_id: value.run_id as string | null,
      sequence: value.sequence as number,
      schema_version: value.schema_version as number,
      created_at: value.created_at as string,
      type: "unknown",
      payload: {
        original_type: originalType,
        display_text: displayText,
      },
    }
  }
  if (entry.type !== "message") return entry
  const parts = entry.payload.parts.map(normalizeMessagePart)
  if (parts.every((part, index) => part === entry.payload.parts[index])) {
    return entry
  }
  return {
    ...entry,
    payload: {
      ...entry.payload,
      parts,
    },
  }
}

function normalizeMessagePart(part: MessagePart): MessagePart {
  const value = part as unknown as Record<string, unknown>
  if (!KNOWN_MESSAGE_PART_TYPES.has(String(value.type)) || value.type === "unknown") {
    const originalType =
      value.type === "unknown" && typeof value.original_type === "string"
        ? value.original_type
        : String(value.type)
    const displayText =
      value.type === "unknown" && typeof value.display_text === "string"
        ? value.display_text
        : "Unsupported conversation content"
    return {
      id: value.id as string,
      type: "unknown",
      original_type: originalType,
      display_text: displayText,
    }
  }
  if (part.type !== "tool_result" || part.output?.type !== "content_parts") {
    return part
  }
  return {
    ...part,
    output: {
      ...part.output,
      parts: part.output.parts.map(normalizeToolOutputContentPart),
    },
  }
}

function normalizeToolOutputContentPart(
  part: ToolOutputContentMessagePart,
): ToolOutputContentMessagePart {
  return normalizeMessagePart(part) as ToolOutputContentMessagePart
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isOptionalNullableString(value: unknown): boolean {
  return value === undefined || value === null || typeof value === "string"
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string"
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
}

function isKnownString(value: unknown, values: ReadonlySet<string>): boolean {
  return typeof value === "string" && values.has(value)
}

function isPositiveInteger(value: unknown): value is number {
  return isNonNegativeInteger(value) && value > 0
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
