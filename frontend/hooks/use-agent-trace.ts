"use client"

import { useCallback, useEffect, useState } from "react"

import {
  getAgentTraceDetail,
  getAgentTraceTimeline,
} from "@/lib/agent/client"
import {
  createAgentTraceDetail,
  createAgentTraceView,
} from "@/lib/agent/projection/trace-projection"
import type {
  AgentTraceEventDetail,
  AgentTraceViewModel,
} from "@/lib/agent/trace-model/types"

export type AgentTraceState = {
  view: AgentTraceViewModel | null
  isLoading: boolean
  error: Error | null
  retry: () => void
  loadDetail: (eventId: string) => Promise<AgentTraceEventDetail>
}

export function useAgentTrace(sessionId: string): AgentTraceState {
  const [loaded, setLoaded] = useState<{
    sessionId: string
    view: AgentTraceViewModel
  } | null>(null)
  const [failure, setFailure] = useState<{
    requestKey: string
    error: Error
  } | null>(null)
  const [retryRevision, setRetryRevision] = useState(0)
  const requestKey = `${sessionId}:${retryRevision}`
  useEffect(() => {
    const controller = new AbortController()
    let active = true

    void getAgentTraceTimeline(sessionId, { signal: controller.signal })
      .then((payload) => {
        if (!active) return
        const projected = createAgentTraceView(payload)
        if (!projected.ok) throw new Error(projected.error.message)
        setLoaded({ sessionId, view: projected.view })
        setFailure((current) =>
          current?.requestKey === requestKey ? null : current,
        )
      })
      .catch((caught) => {
        if (!active || controller.signal.aborted) return
        setFailure({
          requestKey,
          error: asError(caught, "Unable to load Agent Trace"),
        })
      })

    return () => {
      active = false
      controller.abort()
    }
  }, [requestKey, sessionId])

  const loadDetail = useCallback(
    async (eventId: string) => {
      const payload = await getAgentTraceDetail(sessionId, eventId)
      const projected = createAgentTraceDetail(payload)
      if (!projected.ok) throw new Error(projected.error.message)
      return projected.detail
    },
    [sessionId],
  )

  const currentView = loaded?.sessionId === sessionId ? loaded.view : null
  const currentError =
    failure?.requestKey === requestKey ? failure.error : null

  return {
    view: currentView,
    isLoading: currentView === null && currentError === null,
    error: currentError,
    retry: () => setRetryRevision((revision) => revision + 1),
    loadDetail,
  }
}

function asError(value: unknown, fallback: string) {
  return value instanceof Error ? value : new Error(fallback)
}
