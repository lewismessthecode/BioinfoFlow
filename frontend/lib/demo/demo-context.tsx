"use client"

/**
 * Demo replay context.
 *
 * Provides replay state (messages, DAG, run status) to demo page components.
 * Drives the auto-play cinematic experience using the replay engine.
 */

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

import type { AgentCoreEvent, AgentCoreTurn } from "@/lib/agent-core"
import type { DagData, RunStatus } from "@/lib/types"
import {
  parseNDJSON,
  scheduleReplay,
} from "./replay-engine"
import type { DemoAgentReplayEvent, DemoEvent, ReplayStatus } from "./types"

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

type DemoContextValue = {
  /** AgentCore turns accumulated during replay. */
  turns: AgentCoreTurn[]
  /** AgentCore event ledger accumulated during replay. */
  events: AgentCoreEvent[]
  /** Current DAG data. */
  dag: DagData | null
  /** Current run status. */
  runStatus: RunStatus | null
  /** Current task name. */
  currentTask: string | null
  /** Replay status. */
  status: ReplayStatus
  /** 0–1 progress. */
  progress: number
  /** Start or restart playback. */
  play: () => void
  /** Pause playback. */
  pause: () => void
  /** Whether the chat is "streaming" (agent responding). */
  isStreaming: boolean
}

const DemoContext = createContext<DemoContextValue | null>(null)

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

type DemoReplayProviderProps = {
  /** Raw NDJSON text of the recording. */
  recording: string
  /** Auto-start playback on mount. */
  autoPlay?: boolean
  children: ReactNode
}

export function DemoReplayProvider({
  recording,
  autoPlay = true,
  children,
}: DemoReplayProviderProps) {
  const [turns, setTurns] = useState<AgentCoreTurn[]>([])
  const [agentEvents, setAgentEvents] = useState<AgentCoreEvent[]>([])
  const [dag, setDag] = useState<DagData | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [status, setStatus] = useState<ReplayStatus>("idle")
  const [progress, setProgress] = useState(0)
  const [isStreaming, setIsStreaming] = useState(false)

  const cancelRef = useRef<(() => void) | null>(null)
  const activeTurnIdRef = useRef<string | null>(null)
  const turnCounterRef = useRef(0)
  const eventSeqRef = useRef(0)
  const recordedEvents = useMemo(() => parseNDJSON(recording), [recording])

  const createEvent = useCallback((
    turnId: string,
    type: string,
    payload: Record<string, unknown>,
  ): AgentCoreEvent => {
    const timestamp = new Date().toISOString()
    eventSeqRef.current += 1
    return {
      id: `demo-event-${eventSeqRef.current}`,
      session_id: DEMO_AGENT_SESSION_ID,
      turn_id: turnId,
      seq: eventSeqRef.current,
      type,
      payload,
      visibility: "user",
      schema_version: 1,
      created_at: timestamp,
      updated_at: timestamp,
    }
  }, [])

  const startTurn = useCallback((inputText: string) => {
    const timestamp = new Date().toISOString()
    turnCounterRef.current += 1
    const turnId = `demo-turn-${turnCounterRef.current}`
    activeTurnIdRef.current = turnId

    const turn: AgentCoreTurn = {
      id: turnId,
      session_id: DEMO_AGENT_SESSION_ID,
      project_id: "project-demo",
      workspace_id: "workspace-demo",
      user_id: "demo-user",
      input_text: inputText,
      input_parts: null,
      status: "running",
      model_profile_snapshot: {
        profile: "demo-agent-core",
        provider: "demo",
      },
      final_text: "",
      token_usage: null,
      error_code: null,
      error_message: null,
      created_at: timestamp,
      updated_at: timestamp,
      started_at: timestamp,
      completed_at: null,
    }

    const createdEvent = createEvent(turnId, "turn.created", {
      input_text: inputText,
    })
    const startedEvent = createEvent(turnId, "turn.started", {})

    setTurns((prev) => [...prev, turn])
    setAgentEvents((prev) => [...prev, createdEvent, startedEvent])
    return turnId
  }, [createEvent])

  const ensureActiveTurn = useCallback(() => {
    return activeTurnIdRef.current ?? startTurn("Run the BioinfoFlow demo")
  }, [startTurn])

  const applyAgentEvent = useCallback((agentEvent: DemoAgentReplayEvent) => {
    const turnId = ensureActiveTurn()
    const event = createEvent(turnId, agentEvent.type, {
      ...agentEvent.payload,
      source_id: agentEvent.source_id,
    })

    setAgentEvents((prev) => [...prev, event])
    setTurns((prev) =>
      prev.map((turn) => {
        if (turn.id !== turnId) return turn

        const timestamp = new Date().toISOString()
        const next: AgentCoreTurn = {
          ...turn,
          updated_at: timestamp,
        }

        if (agentEvent.final_text_delta) {
          next.final_text = `${next.final_text ?? ""}${agentEvent.final_text_delta}`
        }
        if (agentEvent.final_text !== undefined) {
          next.final_text = agentEvent.final_text
        }
        if (agentEvent.error_message) {
          next.status = "failed"
          next.error_message = agentEvent.error_message
          next.completed_at = timestamp
        } else if (agentEvent.type === "turn.completed") {
          next.status = "completed"
          next.completed_at = timestamp
        }

        return next
      }),
    )

    setIsStreaming(
      agentEvent.type !== "turn.completed" &&
      agentEvent.type !== "turn.failed",
    )
  }, [createEvent, ensureActiveTurn])

  const handleEvent = useCallback((event: DemoEvent, index: number, total: number) => {
    setProgress(total > 0 ? (index + 1) / total : 1)

    switch (event.kind) {
      case "agent":
        applyAgentEvent(event.agentEvent)
        break

      case "user_message":
        startTurn(event.text)
        setIsStreaming(true)
        break

      case "run_status":
        setRunStatus(event.data.status)
        setCurrentTask(event.data.current_task ?? null)
        break

      case "run_dag":
        setDag(event.data.dag)
        break

      case "run_log":
        // Logs are informational — we don't render them in the demo v1
        break
    }
  }, [applyAgentEvent, startTurn])

  const play = useCallback(() => {
    // Cancel any existing playback
    cancelRef.current?.()

    // Reset state
    setTurns([])
    setAgentEvents([])
    setDag(null)
    setRunStatus(null)
    setCurrentTask(null)
    setProgress(0)
    setIsStreaming(false)
    setStatus("playing")
    activeTurnIdRef.current = null
    turnCounterRef.current = 0
    eventSeqRef.current = 0

    cancelRef.current = scheduleReplay(recordedEvents, {
      onEvent: handleEvent,
      onFinish: () => setStatus("finished"),
    })
  }, [recordedEvents, handleEvent])

  const pause = useCallback(() => {
    cancelRef.current?.()
    cancelRef.current = null
    setStatus("paused")
  }, [])

  // Auto-play on mount
  useEffect(() => {
    if (autoPlay) {
      // Small delay so the UI renders before playback starts
      const timer = setTimeout(play, 800)
      return () => clearTimeout(timer)
    }
  }, [autoPlay, play])

  // Cleanup on unmount
  useEffect(() => {
    return () => cancelRef.current?.()
  }, [])

  return (
    <DemoContext.Provider
      value={{
        turns,
        events: agentEvents,
        dag,
        runStatus,
        currentTask,
        status,
        progress,
        play,
        pause,
        isStreaming,
      }}
    >
      {children}
    </DemoContext.Provider>
  )
}

const DEMO_AGENT_SESSION_ID = "agent-session-demo-replay"

// ---------------------------------------------------------------------------
// Hook
// ---------------------------------------------------------------------------

export function useDemoReplay() {
  const ctx = useContext(DemoContext)
  if (!ctx) {
    throw new Error("useDemoReplay must be used inside <DemoReplayProvider>")
  }
  return ctx
}
