import type {
  AgentRuntimeEvent,
  AgentRuntimeTimelineEntry,
  AgentRuntimeToolCallState,
  AgentRuntimeTurn,
} from "./types"

export function buildAgentRuntimeTimeline(
  turns: AgentRuntimeTurn[],
  events: AgentRuntimeEvent[],
): AgentRuntimeTimelineEntry[] {
  const entries = turns.map<AgentRuntimeTimelineEntry>((turn) => ({
    turn,
    assistant: {
      messageId: null,
      text: turn.final_text ?? "",
      status: initialAssistantStatus(turn),
      errorMessage: turn.error_message ?? null,
      thinking: null,
      toolCalls: [],
    },
  }))
  const byTurnId = new Map(entries.map((entry) => [entry.turn.id, entry]))

  for (const event of events) {
    const turnId = event.turn_id ?? null
    if (!turnId) continue
    const entry = byTurnId.get(turnId)
    if (!entry) continue

    switch (event.type) {
      case "assistant.text.delta": {
        entry.assistant.messageId = stringOrNull(event.payload.message_id)
        entry.assistant.text = stringFromPayload(
          firstStringPayload(event.payload, ["content", "text", "delta", "text_delta"]),
          entry.assistant.text,
        )
        entry.assistant.status = "streaming"
        break
      }
      case "assistant.text.completed": {
        entry.assistant.messageId = stringOrNull(event.payload.message_id)
        entry.assistant.text = stringFromPayload(
          firstStringPayload(event.payload, ["content", "text", "delta", "text_delta"]),
          entry.assistant.text,
        )
        entry.assistant.status = "completed"
        break
      }
      case "assistant.thinking.delta": {
        entry.assistant.messageId = stringOrNull(event.payload.message_id)
        entry.assistant.thinking = {
          content: stringFromPayload(
            firstStringPayload(event.payload, ["content", "text", "delta", "text_delta"]),
            entry.assistant.thinking?.content ?? "",
          ),
          isComplete: false,
        }
        break
      }
      case "assistant.thinking.summary":
      case "assistant.thinking.completed": {
        entry.assistant.messageId = stringOrNull(event.payload.message_id)
        entry.assistant.thinking = {
          content: stringFromPayload(
            firstStringPayload(event.payload, ["content", "text", "delta", "text_delta"]),
            entry.assistant.thinking?.content ?? "",
          ),
          isComplete: true,
        }
        break
      }
      case "assistant.tool_call.started":
      case "assistant.tool_call.delta":
      case "assistant.tool_call.completed": {
        entry.assistant.messageId = stringOrNull(event.payload.message_id)
        upsertToolCall(entry.assistant.toolCalls, event)
        break
      }
      case "turn.failed": {
        entry.assistant.status = "failed"
        entry.assistant.errorMessage = stringOrNull(event.payload.error_message)
        break
      }
      case "turn.cancelled":
      case "turn.interrupted": {
        entry.assistant.status = "cancelled"
        break
      }
      case "turn.completed": {
        if (entry.assistant.status !== "failed") {
          entry.assistant.status = "completed"
        }
        break
      }
    }
  }

  return entries
}

function initialAssistantStatus(
  turn: AgentRuntimeTurn,
): AgentRuntimeTimelineEntry["assistant"]["status"] {
  switch (turn.status) {
    case "completed":
      return "completed"
    case "failed":
      return "failed"
    case "cancelled":
      return "cancelled"
    case "queued":
    case "running":
    case "waiting_approval":
    case "waiting_user":
      return "pending"
  }
}

function upsertToolCall(toolCalls: AgentRuntimeToolCallState[], event: AgentRuntimeEvent) {
  const callId = String(event.payload.call_id || "")
  const index = Number(event.payload.index || 0)
  const existing = toolCalls.find((item) => item.callId === callId) ?? null
  const next: AgentRuntimeToolCallState = {
    callId,
    name: String(event.payload.name || existing?.name || ""),
    status: String(event.payload.status || existing?.status || "building"),
    index,
    arguments: isRecord(event.payload.arguments) ? event.payload.arguments : existing?.arguments,
    argumentsDelta: stringOrNull(event.payload.arguments_delta) ?? existing?.argumentsDelta ?? null,
  }
  if (!existing) {
    toolCalls.push(next)
    toolCalls.sort((a, b) => a.index - b.index)
    return
  }
  Object.assign(existing, next)
}

function stringFromPayload(value: unknown, fallback: string) {
  return typeof value === "string" ? value : fallback
}

function firstStringPayload(payload: Record<string, unknown>, keys: string[]) {
  for (const key of keys) {
    const value = payload[key]
    if (typeof value === "string") return value
  }
  return null
}

function stringOrNull(value: unknown) {
  return typeof value === "string" ? value : null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === "object" && !Array.isArray(value)
}
