import type {
  AgentRuntimeEvent,
  AgentRuntimeTimelineEntry,
  AgentRuntimeToolCallState,
  AgentRuntimeTurn,
} from "./types"

type TimelineBuildState = {
  entry: AgentRuntimeTimelineEntry
  textFromEvents: boolean
  thinkingFromEvents: boolean
}

export function buildAgentRuntimeTimeline(
  turns: AgentRuntimeTurn[],
  events: AgentRuntimeEvent[],
): AgentRuntimeTimelineEntry[] {
  const states = turns.map<TimelineBuildState>((turn) => ({
    entry: {
      turn,
      assistant: {
        messageId: null,
        text: turn.final_text ?? "",
        status: initialAssistantStatus(turn),
        errorMessage: turn.error_message ?? null,
        thinking: null,
        toolCalls: [],
      },
    },
    textFromEvents: false,
    thinkingFromEvents: false,
  }))
  const byTurnId = new Map(states.map((state) => [state.entry.turn.id, state]))

  for (const event of events) {
    const turnId = event.turn_id ?? null
    if (!turnId) continue
    const state = byTurnId.get(turnId)
    if (!state) continue
    const { entry } = state

    switch (event.type) {
      case "assistant.text.delta": {
        updateMessageId(entry, event)
        const base = state.textFromEvents ? entry.assistant.text : ""
        const nextText = streamingTextFromPayload(event.payload, base)
        if (nextText !== null) {
          entry.assistant.text = nextText
          state.textFromEvents = true
        }
        entry.assistant.status = "streaming"
        break
      }
      case "assistant.text.completed": {
        updateMessageId(entry, event)
        const base = state.textFromEvents ? entry.assistant.text : ""
        const nextText = completedTextFromPayload(event.payload, base)
        if (nextText !== null) {
          entry.assistant.text = nextText
          state.textFromEvents = true
        }
        entry.assistant.status = "completed"
        break
      }
      case "assistant.thinking.delta": {
        updateMessageId(entry, event)
        const base = state.thinkingFromEvents ? entry.assistant.thinking?.content ?? "" : ""
        const nextThinking = streamingTextFromPayload(event.payload, base)
        if (nextThinking !== null) {
          entry.assistant.thinking = {
            content: nextThinking,
            isComplete: false,
          }
          state.thinkingFromEvents = true
        }
        break
      }
      case "assistant.thinking.summary":
      case "assistant.thinking.completed": {
        updateMessageId(entry, event)
        const base = state.thinkingFromEvents ? entry.assistant.thinking?.content ?? "" : ""
        const nextThinking = completedTextFromPayload(event.payload, base)
        entry.assistant.thinking = {
          content: nextThinking ?? entry.assistant.thinking?.content ?? "",
          isComplete: true,
        }
        if (nextThinking !== null) state.thinkingFromEvents = true
        break
      }
      case "assistant.tool_call.started":
      case "assistant.tool_call.delta":
      case "assistant.tool_call.completed": {
        updateMessageId(entry, event)
        upsertToolCall(entry.assistant.toolCalls, event)
        break
      }
      case "turn.failed": {
        if (entry.assistant.status !== "completed") {
          entry.assistant.status = "failed"
        }
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

  return states.map((state) => state.entry)
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

function updateMessageId(entry: AgentRuntimeTimelineEntry, event: AgentRuntimeEvent) {
  entry.assistant.messageId = stringOrNull(event.payload.message_id) ?? entry.assistant.messageId
}

function streamingTextFromPayload(payload: Record<string, unknown>, current: string) {
  const cumulative = firstStringPayload(payload, ["content", "text"])
  if (cumulative !== null) return cumulative
  const delta = firstStringPayload(payload, ["delta", "text_delta"])
  if (delta !== null) return `${current}${delta}`
  return null
}

function completedTextFromPayload(payload: Record<string, unknown>, current: string) {
  const finalText = firstStringPayload(payload, ["content", "text"])
  if (finalText !== null) return finalText
  const delta = firstStringPayload(payload, ["delta", "text_delta"])
  if (delta !== null) return `${current}${delta}`
  return null
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
