"use client"

import { useCallback, useEffect, useMemo, useRef, useState } from "react"

import type { AgentSessionState } from "@/hooks/use-agent-session"
import {
  applyConversationProjectionEvent,
  createConversationProjection,
} from "@/lib/agent/projection/conversation-projection"
import type { ConversationViewModel } from "@/lib/agent/conversation-model/types"
import type { ConversationProjectionState } from "@/lib/agent/projection/conversation-projection"
import type { DagData, RunStatus } from "@/lib/types"
import { parseNDJSON, scheduleReplay } from "./replay-engine"
import type { DemoTimelineItem, ReplayStatus } from "./types"

export function useDemoReplay(recording: string, autoPlay = true) {
  const timeline = useMemo(() => parseNDJSON(recording), [recording])
  const initialProjection = useMemo(
    () => projectionFromTimeline(timeline),
    [timeline],
  )
  const [projection, setProjection] = useState(initialProjection)
  const [dag, setDag] = useState<DagData | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [status, setStatus] = useState<ReplayStatus>("idle")
  const [progress, setProgress] = useState(0)
  const projectionRef = useRef(initialProjection)
  const cancelRef = useRef<(() => void) | null>(null)

  const applyTimelineItem = useCallback((item: DemoTimelineItem) => {
    if (item.kind === "pipeline") {
      setRunStatus(item.status)
      setCurrentTask(item.currentTask)
      setDag(item.dag)
      return
    }

    const application = applyConversationProjectionEvent(
      projectionRef.current.state,
      item.event,
    )
    if (application.outcome !== "applied") return
    const next = { state: application.state, view: application.view }
    projectionRef.current = next
    setProjection(next)
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
    projectionRef.current = initialProjection
    setProjection(initialProjection)
    setDag(null)
    setRunStatus(null)
    setCurrentTask(null)
    setProgress(0)
    setStatus("playing")
    cancelRef.current = scheduleReplay(timeline, {
      onEvent: handleEvent,
      onFinish: () => setStatus("finished"),
    })
  }, [handleEvent, initialProjection, timeline])

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
      ...projection.state.transportState,
      conversationView: projection.view,
      connectionStatus: "connected",
      error: null,
      isLoading: false,
      sendMessage: async () => {},
      steer: async () => {},
      respond: async () => {},
      cancel: async () => {},
      updatePermissionMode: async () => {},
      updateModel: async () => {},
      updateEnvironmentScope: async () => {},
      retry: play,
    }),
    [play, projection],
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

function projectionFromTimeline(
  timeline: DemoTimelineItem[],
): DemoProjection {
  const snapshotItem = timeline[0]
  if (!snapshotItem || snapshotItem.kind !== "agent") {
    throw new Error("Demo timeline must begin with an Agent snapshot")
  }
  if (snapshotItem.event.type !== "snapshot") {
    throw new Error("Demo timeline snapshot is invalid")
  }
  const projection = createConversationProjection(snapshotItem.event.snapshot)
  if (!projection.ok) {
    throw new Error(projection.diagnostic.message)
  }
  return { state: projection.state, view: projection.view }
}

type DemoProjection = {
  state: ConversationProjectionState
  view: ConversationViewModel
}

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
}
