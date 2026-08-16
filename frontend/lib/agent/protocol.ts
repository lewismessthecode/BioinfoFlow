import type {
  AgentArtifactView as GeneratedAgentArtifact,
  Event as GeneratedAgentEvent,
} from "./protocol.generated"
import type {
  AgentEvent as CanonicalAgentEvent,
  SessionSnapshot,
} from "./contracts"
import {
  isAgentWireArtifact,
  isAgentWireEvent,
  isAgentWireSnapshot,
} from "./protocol-validation"

const AGENT_UI_PROTOCOL_VERSION = 1 as const

export type AgentEvent = CanonicalAgentEvent
export type AgentArtifact = GeneratedAgentArtifact
type AgentWireEvent = GeneratedAgentEvent
export type ProtocolDecodeFailure = "malformed" | "unsupported_version"
export type ProtocolDecodeResult<T> =
  | { ok: true; value: T }
  | { ok: false; reason: ProtocolDecodeFailure }

export function decodeAgentEvent(value: unknown): ProtocolDecodeResult<AgentEvent> {
  if (!isRecord(value)) return malformed()
  if (value.protocol_version !== AGENT_UI_PROTOCOL_VERSION) {
    return typeof value.protocol_version === "number"
      ? { ok: false, reason: "unsupported_version" }
      : malformed()
  }
  return isAgentWireEvent(value)
    ? { ok: true, value: value as unknown as AgentWireEvent as AgentEvent }
    : malformed()
}

export function decodeAgentArtifact(
  value: unknown,
): ProtocolDecodeResult<AgentArtifact> {
  if (!isRecord(value)) return malformed()
  if (value.protocol_version !== AGENT_UI_PROTOCOL_VERSION) {
    return typeof value.protocol_version === "number"
      ? { ok: false, reason: "unsupported_version" }
      : malformed()
  }
  return isAgentWireArtifact(value)
    ? { ok: true, value }
    : malformed()
}

export function decodeAgentSnapshot(
  value: unknown,
): ProtocolDecodeResult<SessionSnapshot> {
  if (!isRecord(value)) return malformed()
  if (value.protocol_version !== AGENT_UI_PROTOCOL_VERSION) {
    return typeof value.protocol_version === "number"
      ? { ok: false, reason: "unsupported_version" }
      : malformed()
  }
  return isAgentWireSnapshot(value)
    ? { ok: true, value: value as unknown as SessionSnapshot }
    : malformed()
}

function malformed(): ProtocolDecodeResult<never> {
  return { ok: false, reason: "malformed" }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value)
}
