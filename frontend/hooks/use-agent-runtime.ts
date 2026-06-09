"use client"

import { useCallback, useEffect, useMemo, useReducer, useRef, useState } from "react"

import {
  agentRuntimeReducer,
  createAgentRuntimeSession,
  createAgentRuntimeTurn,
  decideAgentRuntimeAction,
  getAgentRuntimeState,
  initialAgentRuntimeState,
  interruptAgentRuntimeTurn,
  listAgentRuntimeSessions,
  subscribeAgentRuntimeEvents,
  type AgentModelSelection,
  type AgentRuntimeSession,
} from "@/lib/agent-runtime"
import { getCurrentRuntime } from "@/lib/runtime"

type UseAgentRuntimeOptions = {
  activeSessionId?: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
}

export function useAgentRuntime(
  projectId?: string | null,
  options: UseAgentRuntimeOptions = {},
) {
  const isControlled = Object.prototype.hasOwnProperty.call(options, "activeSessionId")
  const onActiveSessionIdChange = options.onActiveSessionIdChange
  const [sessions, setSessions] = useState<AgentRuntimeSession[]>([])
  const [uncontrolledSessionId, setUncontrolledSessionId] = useState<string | null>(null)
  const [state, dispatch] = useReducer(agentRuntimeReducer, initialAgentRuntimeState)
  const streamCursorRef = useRef(0)
  const activeSessionId = isControlled
    ? options.activeSessionId || null
    : uncontrolledSessionId
  const isControlledDraft = isControlled && options.activeSessionId === ""
  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? state.session,
    [activeSessionId, sessions, state.session],
  )

  const setActiveSessionId = useCallback(
    (sessionId: string | null) => {
      if (isControlled) {
        onActiveSessionIdChange?.(sessionId ?? "")
      } else {
        setUncontrolledSessionId(sessionId)
      }
    },
    [isControlled, onActiveSessionIdChange],
  )

  const refreshSessions = useCallback(async () => {
    dispatch({ type: "loading" })
    try {
      const nextSessions = await listAgentRuntimeSessions(projectId)
      setSessions(nextSessions)
      if (isControlledDraft) {
        dispatch({ type: "session.selected", session: null })
        return
      }
      const nextActive =
        activeSessionId && nextSessions.some((session) => session.id === activeSessionId)
          ? activeSessionId
          : nextSessions[0]?.id ?? null
      setActiveSessionId(nextActive)
      if (!nextActive) dispatch({ type: "session.selected", session: null })
    } catch (error) {
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load sessions",
      })
    }
  }, [activeSessionId, isControlledDraft, projectId, setActiveSessionId])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshSessions()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshSessions])

  const refreshState = useCallback(async (sessionId: string) => {
    dispatch({ type: "loading" })
    try {
      dispatch({ type: "state.loaded", payload: await getAgentRuntimeState(sessionId) })
    } catch (error) {
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load agent state",
      })
    }
  }, [])

  useEffect(() => {
    if (!activeSessionId) return
    void refreshState(activeSessionId)
  }, [activeSessionId, refreshState])

  useEffect(() => {
    streamCursorRef.current = 0
  }, [activeSessionId])

  useEffect(() => {
    streamCursorRef.current = state.events.at(-1)?.seq ?? 0
  }, [state.events])

  useEffect(() => {
    if (!activeSessionId) return
    if (getCurrentRuntime().mode !== "live") return
    return subscribeAgentRuntimeEvents({
      sessionId: activeSessionId,
      afterSeq: streamCursorRef.current,
      onEvent: (event) => {
        streamCursorRef.current = Math.max(streamCursorRef.current, event.seq)
        dispatch({ type: "event.append", event })
      },
    })
  }, [activeSessionId])

  const ensureSession = useCallback(
    async (modelSelection?: AgentModelSelection | null) => {
      if (activeSession) return activeSession
      const created = await createAgentRuntimeSession({
        projectId: projectId || null,
        permissionMode: "guarded_auto",
        modelSelection,
      })
      setSessions((current) => [created, ...current])
      setActiveSessionId(created.id)
      dispatch({ type: "session.selected", session: created })
      return created
    },
    [activeSession, projectId, setActiveSessionId],
  )

  const send = useCallback(
    async (inputText: string, options?: { modelSelection?: AgentModelSelection | null }) => {
      const text = inputText.trim()
      if (!text) return null
      dispatch({ type: "loading" })
      try {
        const session = await ensureSession(options?.modelSelection)
        const turn = await createAgentRuntimeTurn({
          sessionId: session.id,
          inputText: text,
          modelSelection: options?.modelSelection,
        })
        dispatch({ type: "turn.upsert", turn })
        await refreshState(session.id)
        return turn
      } catch (error) {
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Failed to send message",
        })
        return null
      }
    },
    [ensureSession, refreshState],
  )

  const interrupt = useCallback(async () => {
    const running = [...state.turns]
      .reverse()
      .find((turn) => turn.status === "queued" || turn.status === "running")
    if (!running) return null
    const turn = await interruptAgentRuntimeTurn(running.id)
    dispatch({ type: "turn.upsert", turn })
    return turn
  }, [state.turns])

  const decideAction = useCallback(
    async (actionId: string, decision: "approve" | "reject") => {
      try {
        await decideAgentRuntimeAction(actionId, decision)
        if (activeSessionId) await refreshState(activeSessionId)
      } catch (error) {
        dispatch({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to update action decision",
        })
      }
    },
    [activeSessionId, refreshState],
  )

  return {
    sessions,
    session: activeSession,
    state,
    setActiveSessionId,
    refreshSessions,
    refreshState,
    send,
    interrupt,
    decideAction,
  }
}
