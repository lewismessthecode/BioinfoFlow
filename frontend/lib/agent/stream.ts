import { buildApiUrl } from "@/lib/api"
import { connectEventSource } from "@/lib/runtime/event-source-connection"

import type { AgentEvent } from "./contracts"

const INITIAL_BACKOFF_MS = 1_000
const MAX_BACKOFF_MS = 15_000

const AGENT_EVENT_TYPES = [
  "snapshot",
  "run.updated",
  "assistant.delta",
  "tool.updated",
  "interaction.requested",
  "entry.committed",
] as const satisfies readonly AgentEvent["type"][]

export type AgentConnectionStatus =
  | "connecting"
  | "connected"
  | "reconnecting"

export function subscribeAgentEvents(options: {
  sessionId: string
  onEvent: (event: AgentEvent) => void
  onConnectionChange?: (status: AgentConnectionStatus) => void
  onError?: (error: Event) => void
}) {
  options.onConnectionChange?.("connecting")
  return connectEventSource({
    url: () => buildApiUrl(`/agent/sessions/${options.sessionId}/events`),
    eventSourceInit: { withCredentials: true },
    initialBackoffMs: INITIAL_BACKOFF_MS,
    maxBackoffMs: MAX_BACKOFF_MS,
    backoffMultiplier: 2,
    failedSourcePolicy: "close",
    shouldReconnect: () => true,
    onOpen: () => {
      options.onConnectionChange?.("connected")
    },
    onError: (_source, event) => {
      options.onConnectionChange?.("reconnecting")
      options.onError?.(event)
    },
    bindSource: (source) => {
      for (const eventType of AGENT_EVENT_TYPES) {
        source.addEventListener(eventType, (message) => {
          const event = parseAgentEvent(message as MessageEvent)
          if (event?.type === eventType) options.onEvent(event)
        })
      }
    },
  })
}

function parseAgentEvent(message: MessageEvent): AgentEvent | null {
  try {
    const event = JSON.parse(message.data) as AgentEvent
    if (!event || typeof event !== "object" || !("type" in event)) return null
    return event
  } catch {
    return null
  }
}
