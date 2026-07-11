import { buildApiUrl } from "@/lib/api"
import { connectEventSource } from "@/lib/runtime/event-source-connection"
import type { AgentRuntimeEvent } from "./types"

const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 15000

export function subscribeAgentRuntimeEvents(options: {
  sessionId: string
  afterSeq: number
  onEvent: (event: AgentRuntimeEvent) => void
  onReady?: () => void
  onError?: (error: Event) => void
}) {
  let cursor = options.afterSeq

  return connectEventSource({
    url: () =>
      buildApiUrl(`/agent/sessions/${options.sessionId}/stream`, {
        after_seq: cursor,
      }),
    eventSourceInit: { withCredentials: true },
    initialBackoffMs: INITIAL_BACKOFF,
    maxBackoffMs: MAX_BACKOFF,
    backoffMultiplier: 2,
    shouldReconnect: () => true,
    failedSourcePolicy: "close",
    onError: (_source, event) => {
      options.onError?.(event)
    },
    bindSource: (source) => {
      source.addEventListener("ready", () => {
        options.onReady?.()
      })
      source.onmessage = (message) => {
        const event = parseEvent(message as MessageEvent)
        if (!event) return
        cursor = Math.max(cursor, event.seq)
        options.onEvent(event)
      }
      const bindKnownEvent = (eventName: string) => {
        source.addEventListener(eventName, (message) => {
          const event = parseEvent(message as MessageEvent)
          if (!event) return
          cursor = Math.max(cursor, event.seq)
          options.onEvent(event)
        })
      }
      for (const eventName of [
        "turn.created",
        "turn.started",
        "turn.completed",
        "turn.failed",
        "turn.cancelled",
        "turn.interrupted",
        "turn.no_progress",
        "turn.recovery.enqueued",
        "turn.recovery.failed",
        "model.selected",
        "model.retrying",
        "model.fallback",
        "assistant.text.delta",
        "assistant.thinking.summary",
        "assistant.thinking.delta",
        "assistant.thinking.completed",
        "assistant.text.completed",
        "assistant.tool_call.started",
        "assistant.tool_call.delta",
        "assistant.tool_call.completed",
        "action.requested",
        "action.risk_assessed",
        "action.waiting_decision",
        "action.decision_recorded",
        "action.started",
        "action.completed",
        "action.failed",
        "action.cancelled",
        "artifact.created",
        "memory.read",
        "memory.proposed",
        "memory.written",
        "memory.rejected",
      ]) {
        bindKnownEvent(eventName)
      }
    },
  })
}

function parseEvent(message: MessageEvent): AgentRuntimeEvent | null {
  try {
    return JSON.parse(message.data) as AgentRuntimeEvent
  } catch {
    return null
  }
}
