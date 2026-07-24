import type { AgentPublicEventType, AgentRuntimeEvent } from "./types"

export const PUBLIC_AGENT_EVENT_TYPES = [
  "turn.lifecycle",
  "turn.steering",
  "model.lifecycle",
  "assistant.content",
  "assistant.tool_call",
  "action.lifecycle",
  "artifact.created",
  "memory.lifecycle",
] as const satisfies readonly AgentPublicEventType[]

const TURN_LIFECYCLE_TYPES: Record<string, string> = {
  created: "turn.created",
  started: "turn.started",
  completed: "turn.completed",
  failed: "turn.failed",
  cancelled: "turn.cancelled",
  interrupted: "turn.interrupted",
  no_progress: "turn.no_progress",
  recovery_enqueued: "turn.recovery.enqueued",
  recovery_failed: "turn.recovery.failed",
}

const TURN_STEERING_TYPES: Record<string, string> = {
  received: "turn.steer.received",
  delivered: "turn.steer.delivered",
  cancelled: "turn.steer.cancelled",
}

const MODEL_LIFECYCLE_TYPES: Record<string, string> = {
  selected: "model.selected",
  retrying: "model.retrying",
  fallback: "model.fallback",
  warning: "model.warning",
}

const ACTION_LIFECYCLE_TYPES: Record<string, string> = {
  requested: "action.requested",
  risk_assessed: "action.risk_assessed",
  waiting_decision: "action.waiting_decision",
  decision_recorded: "action.decision_recorded",
  started: "action.started",
  completed: "action.completed",
  failed: "action.failed",
  cancelled: "action.cancelled",
}

const MEMORY_LIFECYCLE_TYPES: Record<string, string> = {
  read: "memory.read",
  proposed: "memory.proposed",
  written: "memory.written",
  rejected: "memory.rejected",
}

export function normalizePublicAgentEvent(
  event: AgentRuntimeEvent,
): AgentRuntimeEvent | null {
  if (event.visibility !== "user") return null

  const payload = event.payload
  let normalizedType: string | undefined
  switch (event.type) {
    case "turn.lifecycle":
      normalizedType = TURN_LIFECYCLE_TYPES[stringValue(payload.status)]
      break
    case "turn.steering":
      normalizedType = TURN_STEERING_TYPES[stringValue(payload.status)]
      break
    case "model.lifecycle":
      normalizedType = MODEL_LIFECYCLE_TYPES[stringValue(payload.status)]
      break
    case "assistant.content": {
      const kind = stringValue(payload.kind)
      const phase = stringValue(payload.phase)
      if (kind === "text" && ["delta", "completed"].includes(phase)) {
        normalizedType = `assistant.text.${phase}`
      } else if (
        kind === "thinking" &&
        ["delta", "completed", "summary"].includes(phase)
      ) {
        normalizedType = `assistant.thinking.${phase}`
      }
      break
    }
    case "assistant.tool_call": {
      const phase = stringValue(payload.phase)
      if (["started", "delta", "completed"].includes(phase)) {
        normalizedType = `assistant.tool_call.${phase}`
      }
      break
    }
    case "action.lifecycle":
      normalizedType = ACTION_LIFECYCLE_TYPES[stringValue(payload.status)]
      break
    case "artifact.created":
      normalizedType = "artifact.created"
      break
    case "memory.lifecycle":
      normalizedType = MEMORY_LIFECYCLE_TYPES[stringValue(payload.status)]
      break
  }

  return normalizedType ? { ...event, type: normalizedType } : null
}

function stringValue(value: unknown): string {
  return typeof value === "string" ? value : ""
}
