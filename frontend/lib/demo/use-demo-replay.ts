"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import type { AgentSessionState } from "@/hooks/use-agent-session"
import {
  applyAgentEvent,
  initialAgentStoreState,
  type AgentStoreState,
} from "@/lib/agent/store"
import type { DagData, RunStatus } from "@/lib/types"
import { parseNDJSON, scheduleReplay } from "./replay-engine"
import type { DemoTimelineItem, ReplayStatus } from "./types"

export function useDemoReplay(recording: string, autoPlay = true) {
  const timeline = useMemo(() => parseNDJSON(recording), [recording])
  const initialStore = useMemo(() => storeFromTimeline(timeline), [timeline])
  const [store, setStore] = useState(initialStore)
  const [dag, setDag] = useState<DagData | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [status, setStatus] = useState<ReplayStatus>("idle")
  const [progress, setProgress] = useState(0)
  const storeRef = useRef(initialStore)
  const cancelRef = useRef<(() => void) | null>(null)

  const applyTimelineItem = useCallback((item: DemoTimelineItem) => {
    if (item.kind === "pipeline") {
      setRunStatus(item.status)
      setCurrentTask(item.currentTask)
      setDag(item.dag)
      return
    }

    const application = applyAgentEvent(storeRef.current, item.event)
    if (application.outcome !== "applied") return
    storeRef.current = application.state
    setStore(application.state)
  }, [])

  const handleEvent = useCallback(
    (item: DemoTimelineItem, index: number, total: number) => {
      setProgress(total > 0 ? (index + 1) / total : 1)
      applyTimelineItem(item)
    },
    [applyTimelineItem],
  )

  const play = useCallback(() => {
    cancelRef.current?.()
    storeRef.current = initialStore
    setStore(initialStore)
    setDag(null)
    setRunStatus(null)
    setCurrentTask(null)
    setProgress(0)
    setStatus("playing")
    cancelRef.current = scheduleReplay(timeline, {
      onEvent: handleEvent,
      onFinish: () => setStatus("finished"),
    })
  }, [handleEvent, initialStore, timeline])

  const pause = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
    setStatus("paused")
  }, [])

  useEffect(() => {
    if (!autoPlay || prefersReducedMotion()) return
    const timer = setTimeout(play, 800)
    return () => clearTimeout(timer)
  }, [autoPlay, play])

  useEffect(() => () => cancelRef.current?.(), [])

  const sessionState = useMemo<AgentSessionState>(
    () => ({
      ...store,
      connectionStatus: "connected",
      error: null,
      isLoading: false,
      sendMessage: async () => {},
      steer: async () => {},
      respond: async () => {},
      cancel: async () => {},
      updatePermissionMode: async () => {},
      retry: play,
    }),
    [play, store],
  )

  return {
    sessionState,
    dag,
    runStatus,
    currentTask,
    status,
    progress,
    play,
    pause,
  }
}

function storeFromTimeline(timeline: DemoTimelineItem[]): AgentStoreState {
  const snapshotItem = timeline[0]
  if (!snapshotItem || snapshotItem.kind !== "agent") {
    throw new Error("Demo timeline must begin with an Agent snapshot")
  }
  if (snapshotItem.event.type !== "snapshot") {
    throw new Error("Demo timeline snapshot is invalid")
  }
  return applyAgentEvent(initialAgentStoreState, snapshotItem.event).state
}

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
}
