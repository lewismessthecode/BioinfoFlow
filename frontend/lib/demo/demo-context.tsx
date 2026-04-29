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

import type { ChatMessage } from "@/lib/chat-types"
import type { DagData, RunStatus } from "@/lib/types"
import { applySSEEvent, createClientMessageId, createUserMessage } from "@/lib/chat-utils"
import {
  parseNDJSON,
  scheduleReplay,
} from "./replay-engine"
import type { DemoEvent, ReplayStatus } from "./types"

// ---------------------------------------------------------------------------
// Context shape
// ---------------------------------------------------------------------------

type DemoContextValue = {
  /** Chat messages (accumulated during replay). */
  messages: ChatMessage[]
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
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [dag, setDag] = useState<DagData | null>(null)
  const [runStatus, setRunStatus] = useState<RunStatus | null>(null)
  const [currentTask, setCurrentTask] = useState<string | null>(null)
  const [status, setStatus] = useState<ReplayStatus>("idle")
  const [progress, setProgress] = useState(0)
  const [isStreaming, setIsStreaming] = useState(false)

  const cancelRef = useRef<(() => void) | null>(null)
  const events = useMemo(() => parseNDJSON(recording), [recording])

  const handleEvent = useCallback((event: DemoEvent, index: number, total: number) => {
    setProgress(total > 0 ? (index + 1) / total : 1)

    switch (event.kind) {
      case "agent":
        setIsStreaming(event.sseEvent.type !== "done")
        setMessages((prev) => applySSEEvent(prev, event.sseEvent))
        break

      case "user_message":
        setMessages((prev) => [
          ...prev,
          createUserMessage(createClientMessageId(), event.text),
        ])
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
  }, [])

  const play = useCallback(() => {
    // Cancel any existing playback
    cancelRef.current?.()

    // Reset state
    setMessages([])
    setDag(null)
    setRunStatus(null)
    setCurrentTask(null)
    setProgress(0)
    setIsStreaming(false)
    setStatus("playing")

    cancelRef.current = scheduleReplay(events, {
      onEvent: handleEvent,
      onFinish: () => setStatus("finished"),
    })
  }, [events, handleEvent])

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
        messages,
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
