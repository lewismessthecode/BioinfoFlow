"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { buildApiUrl } from "@/lib/api"
import { emitConversationUpdated } from "@/lib/conversations"
import type {
  AgentEventData,
  EventEnvelope,
  ImageProgressEvent,
  RunDagEvent,
  RunLogEvent,
  RunStatusEvent,
} from "@/lib/types"

export type ConnectionState = "connecting" | "connected" | "reconnecting" | "disconnected"

type UseEventsOptions = {
  projectId?: string | null
  conversationId?: string | null
  runId?: string | null
  imageId?: string | null
  onRunStatus?: (event: EventEnvelope<RunStatusEvent>) => void
  onRunLog?: (event: EventEnvelope<RunLogEvent>) => void
  onRunDag?: (event: EventEnvelope<RunDagEvent>) => void
  onImageProgress?: (event: EventEnvelope<ImageProgressEvent>) => void
  onAgentEvent?: (event: EventEnvelope<AgentEventData>) => void
  onOpen?: () => void
  onError?: (event: Event) => void
}

const parseEnvelope = <T,>(event: MessageEvent): EventEnvelope<T> | null => {
  try {
    return JSON.parse(event.data) as EventEnvelope<T>
  } catch {
    return null
  }
}

const INITIAL_BACKOFF = 1000
const MAX_BACKOFF = 30000
const BACKOFF_MULTIPLIER = 2

export function useEvents({
  projectId,
  conversationId,
  runId,
  imageId,
  onRunStatus,
  onRunLog,
  onRunDag,
  onImageProgress,
  onAgentEvent,
  onOpen,
  onError,
}: UseEventsOptions) {
  const [connectionState, setConnectionState] = useState<ConnectionState>("disconnected")

  const handlersRef = useRef({
    onRunStatus,
    onRunLog,
    onRunDag,
    onImageProgress,
    onAgentEvent,
    onOpen,
    onError,
  })

  useEffect(() => {
    handlersRef.current = {
      onRunStatus,
      onRunLog,
      onRunDag,
      onImageProgress,
      onAgentEvent,
      onOpen,
      onError,
    }
  }, [onRunStatus, onRunLog, onRunDag, onImageProgress, onAgentEvent, onOpen, onError])

  const connect = useCallback(() => {
    if (!projectId) return null

    const url = buildApiUrl("/events/stream", {
      project_id: projectId,
      conversation_id: conversationId || undefined,
      run_id: runId || undefined,
      image_id: imageId || undefined,
    })

    const source = new EventSource(url)
    return source
  }, [projectId, conversationId, runId, imageId])

  useEffect(() => {
    if (!projectId) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setConnectionState("disconnected")
      return
    }

    let source: EventSource | null = null
    let backoff = INITIAL_BACKOFF
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null
    let disposed = false

    const setupSource = () => {
      if (disposed) return

      setConnectionState((prev) => prev === "disconnected" ? "connecting" : "reconnecting")
      source = connect()
      if (!source) return

      source.onopen = () => {
        if (disposed) return
        backoff = INITIAL_BACKOFF
        setConnectionState("connected")
        handlersRef.current.onOpen?.()
      }

      source.onerror = (event) => {
        if (disposed) return
        handlersRef.current.onError?.(event)

        if (source?.readyState === EventSource.CLOSED) {
          setConnectionState("reconnecting")
          source = null
          reconnectTimer = setTimeout(() => {
            backoff = Math.min(backoff * BACKOFF_MULTIPLIER, MAX_BACKOFF)
            setupSource()
          }, backoff)
        }
      }

      const bind = <T,>(eventName: string, handler?: (event: EventEnvelope<T>) => void) => {
        if (!handler || !source) return () => {}
        const listener = (event: MessageEvent) => {
          const envelope = parseEnvelope<T>(event)
          if (!envelope) return
          handler(envelope)
        }
        source.addEventListener(eventName, listener)
        const capturedSource = source
        return () => capturedSource.removeEventListener(eventName, listener)
      }

      bind<RunStatusEvent>("run.status", (payload) =>
        handlersRef.current.onRunStatus?.(payload)
      )
      bind<RunLogEvent>("run.log", (payload) =>
        handlersRef.current.onRunLog?.(payload)
      )
      bind<RunDagEvent>("run.dag", (payload) =>
        handlersRef.current.onRunDag?.(payload)
      )
      bind<ImageProgressEvent>("image.progress", (payload) =>
        handlersRef.current.onImageProgress?.(payload)
      )
      const agentEvents = [
        "agent.thinking", "agent.thinking_content", "agent.plan", "agent.artifact",
        "agent.message", "agent.done", "agent.cancelled", "agent.error",
        "agent.text_delta", "agent.thinking_delta", "agent.tool_call_start", "agent.tool_call_progress", "agent.tool_call_end",
        "agent.approval.requested", "agent.approval.resolved",
      ]
      agentEvents.forEach((eventName) =>
        bind<AgentEventData>(eventName, (payload) => handlersRef.current.onAgentEvent?.(payload))
      )

      // Conversation-level metadata updates (e.g. auto-generated title).
      // Forward directly to the sidebar/bus so the list re-renders without
      // the chat hook having to poll.
      bind<{ title?: string }>("conversation.title_updated", (payload) => {
        if (payload?.conversation_id && payload.data?.title) {
          emitConversationUpdated({
            id: payload.conversation_id,
            project_id: payload.project_id,
            title: payload.data.title,
          })
        }
      })
    }

    setupSource()

    return () => {
      disposed = true
      if (reconnectTimer) clearTimeout(reconnectTimer)
      source?.close()
      setConnectionState("disconnected")
    }
  }, [projectId, conversationId, runId, imageId, connect])

  return { connectionState }
}
