import { buildApiUrl } from "@/lib/api"
import { connectEventSource } from "@/lib/runtime/event-source-connection"
import {
  normalizePublicAgentEvent,
  PUBLIC_AGENT_EVENT_TYPES,
} from "./public-events"
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
        event_view: "public",
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
      const consume = (message: MessageEvent) => {
        const event = parseEvent(message as MessageEvent)
        if (!event) return
        cursor = Math.max(cursor, event.seq)
        const normalized = normalizePublicAgentEvent(event)
        if (normalized) options.onEvent(normalized)
      }
      source.onmessage = consume
      const bindKnownEvent = (eventName: string) => {
        source.addEventListener(eventName, consume)
      }
      for (const eventName of PUBLIC_AGENT_EVENT_TYPES) {
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
