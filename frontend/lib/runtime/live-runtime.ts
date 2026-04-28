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

  let backoff = INITIAL_BACKOFF
  let disposed = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let source: EventSource | null = null

  const bind = <T,>(
    eventSource: EventSource,
    eventName: string,
    handler?: (event: EventEnvelope<T>) => void,
  ) => {
    if (!handler) return
    const listener = (event: MessageEvent) => {
      const envelope = parseEnvelope<T>(event)
      if (!envelope) return
      handler(envelope)
    }
    eventSource.addEventListener(eventName, listener)
  }

  const connect = () => {
    if (disposed) return

    const nextSource = new EventSource(
      buildLiveApiUrl("/events/stream", {
        project_id: options.projectId,
        conversation_id: options.conversationId || undefined,
        run_id: options.runId || undefined,
        image_id: options.imageId || undefined,
      }),
      { withCredentials: true },
    )
    source = nextSource

    nextSource.onopen = () => {
      if (disposed) return
      backoff = INITIAL_BACKOFF
      options.onOpen?.()
    }

    nextSource.onerror = (event) => {
      if (disposed) return
      options.onError?.(event)
      if (nextSource.readyState === EventSource.CLOSED && !reconnectTimer) {
        reconnectTimer = setTimeout(() => {
          reconnectTimer = null
          if (disposed) return
          backoff = Math.min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
          connect()
        }, backoff)
      }
    }

    bind<RunStatusEvent>(nextSource, "run.status", options.onRunStatus)
    bind<RunLogEvent>(nextSource, "run.log", options.onRunLog)
    bind<RunDagEvent>(nextSource, "run.dag", options.onRunDag)
    bind<ImageProgressEvent>(
      nextSource,
      "image.progress",
      options.onImageProgress,
    )

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
      bind<AgentEventData>(nextSource, eventName, options.onAgentEvent)
    })
  }

  connect()

  return () => {
    disposed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    source?.close()
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
