import type { Event as GeneratedAgentEvent } from "./protocol.generated"

export const AGENT_UI_PROTOCOL_VERSION = 1 as const

export type AgentEvent = GeneratedAgentEvent
export type ProtocolDecodeFailure = "malformed" | "unsupported_version"
export type ProtocolDecodeResult<T> =
  | { ok: true; value: T }
  | { ok: false; reason: ProtocolDecodeFailure }

const EVENT_TYPES = new Set([
  "snapshot",
  "run.updated",
  "assistant.delta",
  "tool.updated",
  "interaction.requested",
  "entry.committed",
])

export function decodeAgentEvent(value: unknown): ProtocolDecodeResult<AgentEvent> {
  if (!isRecord(value)) return malformed()
  if (value.protocol_version !== AGENT_UI_PROTOCOL_VERSION) {
    return typeof value.protocol_version === "number"
      ? { ok: false, reason: "unsupported_version" }
      : malformed()
  }
  if (typeof value.type !== "string" || !EVENT_TYPES.has(value.type)) {
    return malformed()
  }

  const valid = (() => {
    switch (value.type) {
      case "snapshot":
        return isRecord(value.snapshot)
      case "run.updated":
        return isRecord(value.run) && isNonEmptyString(value.run.id)
      case "assistant.delta":
        return (
          hasStringFields(value, "run_id", "draft_id", "part_id", "part_type", "delta") &&
          isNonNegativeInteger(value.start_offset) &&
          isNonNegativeInteger(value.end_offset)
        )
      case "tool.updated":
        return hasStringFields(value, "run_id") && isRecord(value.tool) && isNonEmptyString(value.tool.call_id)
      case "interaction.requested":
        return (
          hasStringFields(value, "run_id") &&
          isRecord(value.interaction) &&
          isNonEmptyString(value.interaction.interaction_id)
        )
      case "entry.committed":
        return isRecord(value.entry) && isNonEmptyString(value.entry.id)
      default:
        return false
    }
  })()

  return valid ? { ok: true, value: value as AgentEvent } : malformed()
}

function malformed(): ProtocolDecodeResult<never> {
  return { ok: false, reason: "malformed" }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}

function isNonEmptyString(value: unknown): value is string {
  return typeof value === "string" && value.length > 0
}

function isNonNegativeInteger(value: unknown): value is number {
  return typeof value === "number" && Number.isInteger(value) && value >= 0
}

function hasStringFields(
  value: Record<string, unknown>,
  ...fields: string[]
): boolean {
  return fields.every((field) => isNonEmptyString(value[field]))
}
