type FailedEventSourcePolicy = "retain" | "release" | "close"

export type EventSourceConnectionOptions = {
  url: () => string
  eventSourceInit?: EventSourceInit
  initialBackoffMs: number
  maxBackoffMs: number
  backoffMultiplier: number
  shouldReconnect: (source: EventSource, event: Event) => boolean
  failedSourcePolicy?: FailedEventSourcePolicy
  bindSource?: (source: EventSource) => void
  onConnect?: () => void
  onOpen?: (source: EventSource, event: Event) => void
  onError?: (source: EventSource, event: Event) => void
}

export function connectEventSource(options: EventSourceConnectionOptions) {
  let backoff = options.initialBackoffMs
  let disposed = false
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let source: EventSource | null = null

  const connect = () => {
    if (disposed) return

    options.onConnect?.()
    const nextSource = new EventSource(options.url(), options.eventSourceInit)
    source = nextSource

    nextSource.onopen = (event) => {
      if (disposed) return
      backoff = options.initialBackoffMs
      options.onOpen?.(nextSource, event)
    }

    nextSource.onerror = (event) => {
      if (disposed) return
      options.onError?.(nextSource, event)
      if (disposed) return
      if (!options.shouldReconnect(nextSource, event) || reconnectTimer) return

      const failedSourcePolicy = options.failedSourcePolicy ?? "retain"
      if (failedSourcePolicy === "close") {
        nextSource.close()
      }
      if (failedSourcePolicy !== "retain" && source === nextSource) {
        source = null
      }

      reconnectTimer = setTimeout(() => {
        reconnectTimer = null
        if (disposed) return
        backoff = Math.min(
          backoff * options.backoffMultiplier,
          options.maxBackoffMs,
        )
        connect()
      }, backoff)
    }

    options.bindSource?.(nextSource)
  }

  connect()

  return () => {
    disposed = true
    if (reconnectTimer) {
      clearTimeout(reconnectTimer)
      reconnectTimer = null
    }
    source?.close()
    source = null
  }
}
