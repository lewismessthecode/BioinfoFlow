"use client"

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react"

import type { SessionSnapshot } from "@/lib/agent/contracts"
import {
  applyAgentEvent,
  type AgentStoreState,
} from "@/lib/agent/store"
import type { DagData, RunStatus } from "@/lib/types"
import { parseNDJSON, scheduleReplay } from "./replay-engine"
import type { DemoTimelineItem, ReplayStatus } from "./types"

type DemoContextValue = {
  snapshot: SessionSnapshot
  dag: DagData | null
  runStatus: RunStatus | null
  currentTask: string | null
  status: ReplayStatus
  progress: number
  play: () => void
  pause: () => void
}

const DemoContext = createContext<DemoContextValue | null>(null)

export function DemoReplayProvider({
  recording,
  autoPlay = true,
  children,
}: {
  recording: string
  autoPlay?: boolean
  children: ReactNode
}) {
  const timeline = useMemo(() => parseNDJSON(recording), [recording])
  const initialSnapshot = useMemo(
    () => snapshotFromTimeline(timeline),
    [timeline],
  )
  const [snapshot, setSnapshot] = useState(initialSnapshot)
  const [dag, setDag] = useState<DagData | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [status, setStatus] = useState<ReplayStatus>("idle")
  const [progress, setProgress] = useState(0)
  const storeRef = useRef(storeFromSnapshot(initialSnapshot))
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
    setSnapshot(snapshotFromStore(application.state))
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
    storeRef.current = storeFromSnapshot(initialSnapshot)
    setSnapshot(initialSnapshot)
    setDag(null)
    setRunStatus(null)
    setCurrentTask(null)
    setProgress(0)
    setStatus("playing")
    cancelRef.current = scheduleReplay(timeline, {
      onEvent: handleEvent,
      onFinish: () => setStatus("finished"),
    })
  }, [handleEvent, initialSnapshot, timeline])

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

  return (
    <DemoContext.Provider
      value={{
        snapshot,
        dag,
        runStatus,
        currentTask,
        status,
        progress,
        play,
        pause,
      }}
    >
      {children}
    </DemoContext.Provider>
  )
}

function prefersReducedMotion() {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  )
}

export function useDemoReplay() {
  const context = useContext(DemoContext)
  if (!context) {
    throw new Error("useDemoReplay must be used inside <DemoReplayProvider>")
  }
  return context
}

function snapshotFromTimeline(timeline: DemoTimelineItem[]) {
  const snapshotItem = timeline[0]
  if (!snapshotItem || snapshotItem.kind !== "agent") {
    throw new Error("Demo timeline must begin with an Agent snapshot")
  }
  if (snapshotItem.event.type !== "snapshot") {
    throw new Error("Demo timeline snapshot is invalid")
  }
  return snapshotItem.event.snapshot
}

function storeFromSnapshot(snapshot: SessionSnapshot): AgentStoreState {
  return {
    session: snapshot.session,
    runs: snapshot.runs,
    entries: snapshot.entries,
    activeRun: snapshot.active_run,
  }
}

function snapshotFromStore(store: AgentStoreState): SessionSnapshot {
  if (!store.session) throw new Error("Demo replay session is unavailable")
  return {
    session: store.session,
    runs: store.runs,
    entries: store.entries,
    active_run: store.activeRun,
  }
}
