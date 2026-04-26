import type { AppRuntime, RuntimeEventSubscription } from "./types"

import { buildLiveApiUrl, buildLiveWebSocketUrl, liveRequest } from "./request-core"
import type {
  AgentEventData,
  EventEnvelope,
  ImageProgressEvent,
  RunDagEvent,
  RunLogEvent,
  RunStatusEvent,
} from "@/lib/types"

const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 30000
const BACKOFF_MULTIPLIER = 2

function parseEnvelope<T>(event: MessageEvent): EventEnvelope<T> | null {
  try {
    return JSON.parse(event.data) as EventEnvelope<T>
  } catch {
    return null
  }
}

function subscribeLive(options: RuntimeEventSubscription) {
  if (!options.projectId) return () => {}

  const source = new EventSource(
    buildLiveApiUrl("/events/stream", {
      project_id: options.projectId,
      conversation_id: options.conversationId || undefined,
      run_id: options.runId || undefined,
      image_id: options.imageId || undefined,
    }),
  )

  let backoff = INITIAL_BACKOFF
  let disposed = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null

  const bind = <T,>(
    eventName: string,
    handler?: (event: EventEnvelope<T>) => void,
  ) => {
    if (!handler) return
    const listener = (event: MessageEvent) => {
      const envelope = parseEnvelope<T>(event)
      if (!envelope) return
      handler(envelope)
    }
    source.addEventListener(eventName, listener)
  }

  source.onopen = () => {
    if (disposed) return
    backoff = INITIAL_BACKOFF
    options.onOpen?.()
  }

  source.onerror = (event) => {
    if (disposed) return
    options.onError?.(event)
    if (source.readyState === EventSource.CLOSED) {
      reconnectTimer = setTimeout(() => {
        backoff = Math.min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
      }, backoff)
    }
  }

  bind<RunStatusEvent>("run.status", options.onRunStatus)
  bind<RunLogEvent>("run.log", options.onRunLog)
  bind<RunDagEvent>("run.dag", options.onRunDag)
  bind<ImageProgressEvent>("image.progress", options.onImageProgress)

  const agentEvents = [
    "agent.thinking",
    "agent.thinking_content",
    "agent.plan",
    "agent.artifact",
    "agent.message",
    "agent.done",
    "agent.cancelled",
    "agent.error",
    "agent.text_delta",
    "agent.thinking_delta",
    "agent.tool_call_start",
    "agent.tool_call_progress",
    "agent.tool_call_end",
    "agent.approval.requested",
    "agent.approval.resolved",
  ] as const

  agentEvents.forEach((eventName) => {
    bind<AgentEventData>(eventName, options.onAgentEvent)
  })

  return () => {
    disposed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    source.close()
  }
}

export function createLiveRuntime(): AppRuntime {
  return {
    mode: "live",
    capabilities: {
      auth: true,
      terminal: true,
      destructiveActions: true,
    },
    request: liveRequest,
    buildApiUrl: buildLiveApiUrl,
    buildWebSocketUrl: buildLiveWebSocketUrl,
    subscribe: subscribeLive,
  }
}
