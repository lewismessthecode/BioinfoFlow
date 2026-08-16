import type {
  AgentArtifactView as AgentWireArtifact,
  Event as AgentWireEvent,
  SessionSnapshot as AgentWireSnapshot,
} from "./protocol.generated"

const PERMISSION_MODES = new Set([
  "ask_changes",
  "ask_dangerous",
  "full_access",
])
const WORKSPACE_ACCESS = new Set(["read_only", "read_write"])
const SESSION_STATUSES = new Set(["active", "archived", "closing", "deleted"])
const RUN_STATUSES = new Set([
  "queued",
  "running",
  "waiting_user",
  "completed",
  "failed",
  "cancelled",
])
const RUN_PHASES = new Set(["model", "tools", "interaction"])
const TOOL_STATUSES = new Set([
  "pending",
  "running",
  "completed",
  "failed",
  "blocked",
  "cancelled",
  "interaction_required",
])
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
const EXECUTION_MODES = new Set(["parallel", "serial", "mixed"])
const DETAIL_KINDS = new Set([
  "command",
  "working_directory",
  "path",
  "input",
  "output",
  "changes",
  "error",
  "metadata",
])
const DETAIL_FORMATS = new Set(["text", "code", "path", "json", "diff"])
const DRAFT_PART_TYPES = new Set(["text", "reasoning_summary"])
const EXECUTION_SCOPE_MODES = new Set(["auto", "manual"])
const TARGET_KINDS = new Set(["local", "remote_ssh"])
const TARGET_STATUSES = new Set(["online", "offline", "error", "unknown"])
const MESSAGE_ROLES = new Set(["user", "assistant", "tool"])
const PLAN_STATUSES = new Set(["pending", "in_progress", "completed"])
const RECOVERY_CHOICES = new Set(["inspect", "retry", "cancel"])

export function isAgentWireEvent(value: unknown): value is AgentWireEvent {
  if (!isRecord(value) || value.protocol_version !== 1 || typeof value.type !== "string") {
    return false
  }
  switch (value.type) {
    case "snapshot":
      return isAgentWireSnapshot(value.snapshot)
    case "run.updated":
      return isRun(value.run)
    case "assistant.delta":
      return (
        hasStrings(value, "run_id", "draft_id", "part_id", "delta") &&
        isOneOf(value.part_type, DRAFT_PART_TYPES) &&
        isNonNegativeInteger(value.start_offset) &&
        isNonNegativeInteger(value.end_offset)
      )
    case "tool.updated":
      return isNonEmptyString(value.run_id) && isToolProgress(value.tool)
    case "interaction.requested":
      return isNonEmptyString(value.run_id) && isPendingInteraction(value.interaction)
    case "entry.committed":
      return isHistoryEntry(value.entry)
    default:
      return false
  }
}

export function isAgentWireArtifact(value: unknown): value is AgentWireArtifact {
  return (
    isRecord(value) &&
    value.protocol_version === 1 &&
    hasStrings(
      value,
      "id",
      "session_id",
      "type",
      "title",
      "created_at",
      "updated_at",
    ) &&
    isNullableString(value.run_id) &&
    isNullableString(value.summary) &&
    (value.payload === null || isRecord(value.payload)) &&
    (value.resource_ref === null || isStoredArtifactResource(value.resource_ref))
  )
}

function isStoredArtifactResource(value: unknown): boolean {
  return (
    isRecord(value) &&
    value.kind === "stored_file" &&
    hasStrings(value, "filename", "mime_type", "sha256") &&
    isNonNegativeInteger(value.size_bytes)
  )
}

export function isAgentWireSnapshot(value: unknown): value is AgentWireSnapshot {
  return (
    isRecord(value) &&
    value.protocol_version === 1 &&
    isSession(value.session) &&
    Array.isArray(value.runs) &&
    value.runs.every(isRun) &&
    Array.isArray(value.entries) &&
    value.entries.every(isHistoryEntry) &&
    (value.active_run === null || isActiveRun(value.active_run))
  )
}

function isSession(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "user_id", "workspace_id", "created_at", "updated_at") &&
    isNullableString(value.project_id) &&
    isNullableString(value.title) &&
    isModel(value.model) &&
    isOneOf(value.permission_mode, PERMISSION_MODES) &&
    isOneOf(value.workspace_access, WORKSPACE_ACCESS) &&
    isOneOf(value.status, SESSION_STATUSES) &&
    (value.execution_scope === undefined || isExecutionScope(value.execution_scope))
  )
}

function isModel(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "provider", "model", "display_name") &&
    typeof value.supports_vision === "boolean" &&
    typeof value.supports_reasoning === "boolean" &&
    typeof value.supports_tools === "boolean" &&
    (value.catalog_model_id === undefined || isNullableString(value.catalog_model_id))
  )
}

function isExecutionScope(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !isOneOf(value.mode, EXECUTION_SCOPE_MODES) ||
    !Array.isArray(value.target_ids) ||
    !value.target_ids.every(isNonEmptyString)
  ) {
    return false
  }
  return value.mode !== "manual" || value.target_ids.length > 0
}

function isRun(value: unknown): boolean {
  if (
    !isRecord(value) ||
    !hasStrings(value, "id", "session_id", "created_at", "updated_at") ||
    !isOneOf(value.status, RUN_STATUSES) ||
    !(value.phase === null || isOneOf(value.phase, RUN_PHASES)) ||
    !isNonNegativeInteger(value.revision) ||
    !isNullableString(value.started_at) ||
    !isNullableString(value.completed_at) ||
    !isNullableString(value.termination_reason) ||
    !(value.error === null || isRunError(value.error)) ||
    !(
      value.settings === undefined ||
      value.settings === null ||
      isRunSettings(value.settings)
    )
  ) {
    return false
  }
  return value.status === "failed" ? value.error !== null : value.error === null
}

function isRunError(value: unknown): boolean {
  return isRecord(value) && hasStrings(value, "code", "message")
}

function isRunSettings(value: unknown): boolean {
  return (
    isRecord(value) &&
    isModel(value.model) &&
    isOneOf(value.permission_mode, PERMISSION_MODES) &&
    isExecutionScope(value.execution_scope) &&
    Array.isArray(value.allowed_targets) &&
    value.allowed_targets.every(isExecutionTarget)
  )
}

function isExecutionTarget(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "handle", "alias") &&
    isOneOf(value.kind, TARGET_KINDS) &&
    isOneOf(value.status, TARGET_STATUSES) &&
    typeof value.primary === "boolean" &&
    isNullableString(value.disabled_reason)
  )
}

function isActiveRun(value: unknown): boolean {
  return (
    isRecord(value) &&
    isRun(value.run) &&
    (value.assistant_draft === null || isAssistantDraft(value.assistant_draft)) &&
    Array.isArray(value.tool_progress) &&
    value.tool_progress.every(isToolProgress) &&
    (value.pending_interaction === null || isPendingInteraction(value.pending_interaction))
  )
}

function isAssistantDraft(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "run_id") &&
    Array.isArray(value.parts) &&
    value.parts.every(
      (part) =>
        isRecord(part) &&
        hasStrings(part, "id", "text") &&
        isOneOf(part.type, DRAFT_PART_TYPES) &&
        isNonNegativeInteger(part.end_offset),
    )
  )
}

function isToolProgress(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "call_id", "group_id", "name", "display_name", "summary") &&
    isOneOf(value.execution_mode, EXECUTION_MODES) &&
    isOneOf(value.category, TOOL_CATEGORIES) &&
    isRecord(value.arguments) &&
    isOneOf(value.status, TOOL_STATUSES) &&
    isNonNegativeInteger(value.revision) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableString(value.input_summary) &&
    isNullableString(value.output_summary) &&
    isNullableString(value.error) &&
    (value.public_details === undefined ||
      (Array.isArray(value.public_details) && value.public_details.every(isToolDetail))) &&
    (value.target === undefined || value.target === null || isToolTarget(value.target))
  )
}

function isToolDetail(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "value") &&
    isOneOf(value.kind, DETAIL_KINDS) &&
    isNullableString(value.label) &&
    isOneOf(value.format, DETAIL_FORMATS) &&
    typeof value.copyable === "boolean" &&
    typeof value.truncated === "boolean" &&
    typeof value.redacted === "boolean"
  )
}

function isToolTarget(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "handle", "alias") &&
    isOneOf(value.kind, TARGET_KINDS) &&
    (value.root === undefined || isNullableString(value.root))
  )
}

function isPendingInteraction(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "interaction_id", "run_id") &&
    isPositiveInteger(value.revision) &&
    isInteractionRequest(value.request)
  )
}

function isInteractionRequest(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string" || !isNonEmptyString(value.call_id)) {
    return false
  }
  if (value.type === "ask_user") {
    return (
      Array.isArray(value.questions) &&
      value.questions.length >= 1 &&
      value.questions.length <= 3 &&
      value.questions.every(isAskUserQuestion)
    )
  }
  if (value.type === "approval") {
    return (
      hasStrings(value, "tool_name", "summary") &&
      isNullableString(value.input_preview) &&
      Array.isArray(value.allowed_responses) &&
      value.allowed_responses.length > 0 &&
      value.allowed_responses.every((item) => item === "approve" || item === "reject") &&
      isApprovalRisk(value.risk) &&
      (value.target === undefined || value.target === null || isToolTarget(value.target))
    )
  }
  return (
    value.type === "recovery" &&
    hasStrings(value, "tool_name", "message") &&
    Array.isArray(value.options) &&
    value.options.every(isInteractionOption)
  )
}

function isAskUserQuestion(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "id", "header", "question") &&
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
    hasStrings(value, "id", "label", "description") &&
    typeof value.recommended === "boolean"
  )
}

function isApprovalRisk(value: unknown): boolean {
  return (
    isRecord(value) &&
    isNonEmptyString(value.level) &&
    isStringArray(value.effects) &&
    isStringArray(value.reasons) &&
    isStringArray(value.affected_resources)
  )
}

function isHistoryEntry(value: unknown): boolean {
  if (!isRecord(value) || !isHistoryEntryBase(value) || typeof value.type !== "string") {
    return false
  }
  switch (value.type) {
    case "message":
      return isMessagePayload(value.payload)
    case "interaction_request":
      return (
        isRecord(value.payload) &&
        isNonEmptyString(value.payload.interaction_id) &&
        isInteractionRequest(value.payload.request)
      )
    case "interaction_response":
      return (
        isRecord(value.payload) &&
        isNonEmptyString(value.payload.interaction_id) &&
        isInteractionResponse(value.payload.response)
      )
    case "notice":
      return (
        isRecord(value.payload) &&
        hasStrings(value.payload, "code", "message") &&
        "details" in value.payload
      )
    case "plan":
      return isPlanPayload(value.payload)
    default:
      return false
  }
}

function isHistoryEntryBase(value: Record<string, unknown>): boolean {
  return (
    hasStrings(value, "id", "session_id", "created_at") &&
    isNullableString(value.run_id) &&
    isPositiveInteger(value.sequence) &&
    isPositiveInteger(value.schema_version)
  )
}

function isMessagePayload(value: unknown): boolean {
  return (
    isRecord(value) &&
    isOneOf(value.role, MESSAGE_ROLES) &&
    Array.isArray(value.parts) &&
    value.parts.every(isMessagePart)
  )
}

function isMessagePart(value: unknown): boolean {
  if (!isRecord(value) || !isNonEmptyString(value.id) || typeof value.type !== "string") {
    return false
  }
  switch (value.type) {
    case "text":
    case "reasoning_summary":
      return typeof value.text === "string"
    case "attachment_ref":
      return (
        hasStrings(value, "attachment_id", "filename", "kind") &&
        isNullableString(value.mime_type) &&
        isNonNegativeInteger(value.size_bytes)
      )
    case "file_ref":
    case "directory_ref":
      return (
        isNonEmptyString(value.label) &&
        isOptionalNullableString(value.project_id) &&
        isOptionalNullableString(value.attachment_id) &&
        isOptionalNullableString(value.path)
      )
    case "workflow_ref":
      return hasStrings(value, "workflow_id", "label") && isOptionalNullableString(value.project_id)
    case "run_ref":
      return hasStrings(value, "run_id", "label")
    case "artifact_ref":
      return (
        isNonEmptyString(value.artifact_id) &&
        isNullableString(value.title) &&
        isNullableString(value.media_type)
      )
    case "tool_call":
      return isToolCallPart(value)
    case "tool_result":
      return isToolResultPart(value)
    case "unknown":
      return hasStrings(value, "original_type", "display_text")
    default:
      return false
  }
}

function isToolCallPart(value: Record<string, unknown>): boolean {
  return (
    hasStrings(value, "call_id", "group_id", "name", "display_name", "summary") &&
    isOneOf(value.execution_mode, EXECUTION_MODES) &&
    isOneOf(value.category, TOOL_CATEGORIES) &&
    isRecord(value.arguments) &&
    (value.public_details === undefined ||
      (Array.isArray(value.public_details) && value.public_details.every(isToolDetail)))
  )
}

function isToolResultPart(value: Record<string, unknown>): boolean {
  return (
    isNonEmptyString(value.call_id) &&
    isOneOf(value.status, TOOL_STATUSES) &&
    isNullableString(value.summary) &&
    (value.output === null || isToolOutput(value.output)) &&
    isNullableString(value.started_at) &&
    isNullableString(value.completed_at) &&
    isNullableString(value.error) &&
    (value.public_details === undefined ||
      (Array.isArray(value.public_details) && value.public_details.every(isToolDetail)))
  )
}

function isToolOutput(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false
  if (value.type === "text") return typeof value.text === "string"
  if (value.type === "json") return "value" in value
  return (
    value.type === "content_parts" &&
    Array.isArray(value.parts) &&
    value.parts.every(
      (part) => isRecord(part) && part.type !== "tool_call" && part.type !== "tool_result" && isMessagePart(part),
    )
  )
}

function isInteractionResponse(value: unknown): boolean {
  if (!isRecord(value) || typeof value.type !== "string") return false
  if (value.type === "ask_user") return isRecord(value.answers)
  if (value.type === "approval") return typeof value.approved === "boolean"
  return value.type === "recovery" && isOneOf(value.choice, RECOVERY_CHOICES)
}

function isPlanPayload(value: unknown): boolean {
  return (
    isRecord(value) &&
    hasStrings(value, "plan_id", "updated_at") &&
    isPositiveInteger(value.revision) &&
    isOptionalNullableString(value.title) &&
    Array.isArray(value.items) &&
    value.items.every(
      (item) =>
        isRecord(item) &&
        hasStrings(item, "id", "text") &&
        isOneOf(item.status, PLAN_STATUSES),
    )
  )
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0
}

function hasStrings(value: Record<string, unknown>, ...fields: string[]): boolean {
  return fields.every((field) => isNonEmptyString(value[field]))
}

function isNullableString(value: unknown): boolean {
  return value === null || typeof value === "string"
}

function isOptionalNullableString(value: unknown): boolean {
  return value === undefined || isNullableString(value)
}

function isStringArray(value: unknown): boolean {
  return Array.isArray(value) && value.every((item) => typeof item === "string")
}

function isNonNegativeInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
}

function isPositiveInteger(value: unknown): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= 1
}

function isOneOf(value: unknown, choices: ReadonlySet<string>): boolean {
  return typeof value === "string" && choices.has(value)
}
