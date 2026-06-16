import { buildApiUrl } from "@/lib/api"
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
  let disposed = false
  let source: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let backoff = INITIAL_BACKOFF
  let cursor = options.afterSeq

  const connect = () => {
    if (disposed) return
    source = new EventSource(
      buildApiUrl(`/agent/sessions/${options.sessionId}/stream`, {
        after_seq: cursor,
      }),
      { withCredentials: true },
    )
    source.onopen = () => {
      backoff = INITIAL_BACKOFF
    }
    source.onerror = (event) => {
      options.onError?.(event)
      if (disposed || reconnectTimer) return
      source?.close()
      source = null
      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        backoff = Math.min(backoff * 2, MAX_BACKOFF)
        connect()
      }, backoff)
    }
    source.addEventListener("ready", () => {
      options.onReady?.()
    })
    source.onmessage = (message) => {
      const event = parseEvent(message)
      if (!event) return
      cursor = Math.max(cursor, event.seq)
      options.onEvent(event)
    }
    const bindKnownEvent = (eventName: string) => {
      source?.addEventListener(eventName, (message) => {
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
  }

  connect()

  return () => {
    disposed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    source?.close()
  }
}

function parseEvent(message: MessageEvent): AgentRuntimeEvent | null {
  try {
    return JSON.parse(message.data) as AgentRuntimeEvent
  } catch {
    return null
  }
}
