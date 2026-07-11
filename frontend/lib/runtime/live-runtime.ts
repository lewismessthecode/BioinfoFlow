import type { AppRuntime, RuntimeEventSubscription } from "./types"

import { connectEventSource } from "./event-source-connection"
import { buildLiveApiUrl, buildLiveWebSocketUrl, liveRequest } from "./request-core"
import type {
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

  return connectEventSource({
    url: () =>
      buildLiveApiUrl("/events/stream", {
        project_id: options.projectId,
        run_id: options.runId || undefined,
        image_id: options.imageId || undefined,
      }),
    eventSourceInit: { withCredentials: true },
    initialBackoffMs: INITIAL_BACKOFF,
    maxBackoffMs: MAX_BACKOFF,
    backoffMultiplier: BACKOFF_MULTIPLIER,
    shouldReconnect: (source) => source.readyState === EventSource.CLOSED,
    failedSourcePolicy: "retain",
    onOpen: () => {
      options.onOpen?.()
    },
    onError: (_source, event) => {
      options.onError?.(event)
    },
    bindSource: (source) => {
      bind<RunStatusEvent>(source, "run.status", options.onRunStatus)
      bind<RunLogEvent>(source, "run.log", options.onRunLog)
      bind<RunDagEvent>(source, "run.dag", options.onRunDag)
      bind<ImageProgressEvent>(
        source,
        "image.progress",
        options.onImageProgress,
      )
    },
  })
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
