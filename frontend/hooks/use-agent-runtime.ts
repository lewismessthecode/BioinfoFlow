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
  updateAgentRuntimeSessionMetadata,
  updateAgentRuntimeSessionMode,
  updateAgentRuntimeSessionPermissionMode,
  type AgentActionDecision,
  type AgentAnswer,
  type AgentMode,
  type AgentModelSelection,
  type AgentPermissionMode,
  type AgentRuntimeInputPart,
  type AgentRuntimeSession,
} from "@/lib/agent-runtime"
import { emitAgentSessionUpdated } from "@/lib/agent-core/session-storage"
import { getCurrentRuntime } from "@/lib/runtime"

type UseAgentRuntimeOptions = {
  activeSessionId?: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
}

type AgentRuntimeStreamStatus = "idle" | "connecting" | "connected" | "reconnecting"
type AgentRuntimeStreamSignal = {
  sessionId: string
  status: Exclude<AgentRuntimeStreamStatus, "idle" | "connecting">
}

const DRAFT_PERMISSION_MODE_STORAGE_KEY = "bioinfoflow.agentRuntime.permissionMode"
const DEFAULT_PERMISSION_MODE: AgentPermissionMode = "guarded_auto"

export function useAgentRuntime(
  projectId?: string | null,
  options: UseAgentRuntimeOptions = {},
) {
  const isControlled = Object.prototype.hasOwnProperty.call(options, "activeSessionId")
  const onActiveSessionIdChange = options.onActiveSessionIdChange
  const [sessions, setSessions] = useState<AgentRuntimeSession[]>([])
  const [uncontrolledSessionId, setUncontrolledSessionId] = useState<string | null>(null)
  const [state, dispatch] = useReducer(agentRuntimeReducer, initialAgentRuntimeState)
  const [eventWindow, setEventWindow] = useState<{
    sessionId: string
    limited: boolean
  } | null>(null)
  const [streamSignal, setStreamSignal] = useState<AgentRuntimeStreamSignal | null>(
    null,
  )
  // Mode chosen for the *next* session; once a session exists its own toolset
  // policy is the source of truth (and exit_plan_mode can flip it server-side).
  const [draftMode, setDraftMode] = useState<AgentMode>("execution")
  const [draftPermissionMode, setDraftPermissionModeState] = useState<AgentPermissionMode>(
    readDraftPermissionMode,
  )
  const streamCursorRef = useRef(0)
  const activeSessionId = isControlled
    ? options.activeSessionId || null
    : uncontrolledSessionId
  const isLiveRuntime = getCurrentRuntime().mode === "live"
  const streamStatus: AgentRuntimeStreamStatus =
    activeSessionId && isLiveRuntime
      ? streamSignal?.sessionId === activeSessionId
        ? streamSignal.status
        : "connecting"
      : "idle"
  const activeSessionIdRef = useRef<string | null>(activeSessionId)
  const lastSessionResetRef = useRef<string | null>(null)
  const isControlledDraft = isControlled && options.activeSessionId === ""
  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? state.session,
    [activeSessionId, sessions, state.session],
  )
  const streamCanStart =
    !activeSessionId || eventWindow?.sessionId === activeSessionId

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
      setSessions((current) => mergeFetchedSessions(current, nextSessions))
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
    activeSessionIdRef.current = activeSessionId
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSessionId) {
      lastSessionResetRef.current = null
      return
    }
    if (state.session?.id === activeSessionId) {
      lastSessionResetRef.current = activeSessionId
      return
    }
    if (lastSessionResetRef.current === activeSessionId) return
    lastSessionResetRef.current = activeSessionId
    dispatch({
      type: "session.loading",
      session: sessions.find((session) => session.id === activeSessionId) ?? null,
    })
  }, [activeSessionId, sessions, state.session?.id])

  useEffect(() => {
    const timer = window.setTimeout(() => {
      void refreshSessions()
    }, 0)
    return () => window.clearTimeout(timer)
  }, [refreshSessions])

  const refreshState = useCallback(async (sessionId: string) => {
    dispatch({ type: "loading" })
    try {
      const payload = await getAgentRuntimeState(sessionId)
      if (activeSessionIdRef.current !== sessionId) return
      setEventWindow({
        sessionId,
        limited: false,
      })
      setSessions((current) => mergeSessionList(current, payload.session))
      emitRuntimeSessionUpdated(payload.session)
      dispatch({ type: "state.loaded", payload })
    } catch (error) {
      if (activeSessionIdRef.current !== sessionId) return
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load agent state",
      })
    }
  }, [])

  useEffect(() => {
    if (!activeSessionId) return
    const timer = window.setTimeout(() => {
      void refreshState(activeSessionId)
    }, 0)
    return () => window.clearTimeout(timer)
  }, [activeSessionId, refreshState])

  useEffect(() => {
    streamCursorRef.current = 0
  }, [activeSessionId])

  useEffect(() => {
    streamCursorRef.current = state.events.at(-1)?.seq ?? 0
  }, [state.events])

  useEffect(() => {
    if (!activeSessionId) return
    if (!isLiveRuntime) return
    if (!streamCanStart) return
    return subscribeAgentRuntimeEvents({
      sessionId: activeSessionId,
      afterSeq: streamCursorRef.current,
      onReady: () => {
        setStreamSignal({ sessionId: activeSessionId, status: "connected" })
        void refreshState(activeSessionId)
      },
      onError: () => {
        setStreamSignal({ sessionId: activeSessionId, status: "reconnecting" })
      },
      onEvent: (event) => {
        setStreamSignal({ sessionId: activeSessionId, status: "connected" })
        streamCursorRef.current = Math.max(streamCursorRef.current, event.seq)
        dispatch({ type: "event.append", event })
      },
    })
  }, [activeSessionId, isLiveRuntime, refreshState, streamCanStart])

  const ensureSessionWithMetadata = useCallback(
    async (
      modelSelection?: AgentModelSelection | null,
      metadata?: Record<string, unknown>,
    ) => {
      if (activeSession) return activeSession
      const created = await createAgentRuntimeSession({
        projectId: projectId || null,
        permissionMode: draftPermissionMode,
        mode: draftMode,
        modelSelection,
        metadata,
      })
      setSessions((current) => [created, ...current])
      activeSessionIdRef.current = created.id
      setActiveSessionId(created.id)
      dispatch({ type: "session.selected", session: created })
      return created
    },
    [activeSession, draftMode, draftPermissionMode, projectId, setActiveSessionId],
  )

  const ensureSessionRemoteConnection = useCallback(
    async (session: AgentRuntimeSession, remoteConnectionId?: string | null) => {
      if (remoteConnectionId === undefined) return session
      if (session.metadata?.remote_connection_id === remoteConnectionId) return session
      if (!remoteConnectionId && !session.metadata?.remote_connection_id) return session
      const metadata = { ...(session.metadata ?? {}) }
      if (remoteConnectionId) {
        metadata.remote_connection_id = remoteConnectionId
      } else {
        delete metadata.remote_connection_id
      }
      const updated = await updateAgentRuntimeSessionMetadata(session.id, {
        ...metadata,
      })
      setSessions((current) => mergeSessionList(current, updated))
      if (activeSessionIdRef.current === updated.id) {
        dispatch({ type: "session.selected", session: updated })
      }
      emitRuntimeSessionUpdated(updated)
      return updated
    },
    [],
  )

  const send = useCallback(
    async (
      inputText: string,
      options?: {
        modelSelection?: AgentModelSelection | null
        inputParts?: AgentRuntimeInputPart[] | null
        remoteConnectionId?: string | null
      },
    ) => {
      const text = inputText.trim()
      if (!text) return null
      dispatch({ type: "loading" })
      try {
        const remoteConnectionId = Object.hasOwn(options ?? {}, "remoteConnectionId")
          ? options?.remoteConnectionId
          : undefined
        const metadata = remoteConnectionId
          ? { remote_connection_id: remoteConnectionId }
          : undefined
        const session = await ensureSessionRemoteConnection(
          await ensureSessionWithMetadata(options?.modelSelection, metadata),
          remoteConnectionId,
        )
        const turn = await createAgentRuntimeTurn({
          sessionId: session.id,
          inputText: text,
          inputParts: options?.inputParts,
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
    [ensureSessionRemoteConnection, ensureSessionWithMetadata, refreshState],
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
    async (
      actionId: string,
      decision: AgentActionDecision,
      options?: { answer?: AgentAnswer; note?: string },
    ) => {
      try {
        await decideAgentRuntimeAction(actionId, {
          decision,
          answer: options?.answer,
          note: options?.note,
        })
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

  const sessionMode: AgentMode =
    ((activeSession?.toolset_policy?.name as AgentMode | undefined) ?? draftMode) === "plan"
      ? "plan"
      : "execution"
  const permissionMode: AgentPermissionMode =
    activeSession?.permission_mode ?? draftPermissionMode

  const setMode = useCallback(
    async (mode: AgentMode) => {
      setDraftMode(mode)
      if (!activeSessionId) return
      try {
        await updateAgentRuntimeSessionMode(activeSessionId, mode)
        await refreshState(activeSessionId)
      } catch (error) {
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Failed to switch mode",
        })
      }
    },
    [activeSessionId, refreshState],
  )

  const setPermissionMode = useCallback(
    async (mode: AgentPermissionMode) => {
      setDraftPermissionModeState(mode)
      writeDraftPermissionMode(mode)
      if (!activeSessionId) return
      try {
        const updated = await updateAgentRuntimeSessionPermissionMode(activeSessionId, mode)
        setSessions((current) =>
          current.map((session) => (session.id === updated.id ? updated : session)),
        )
        await refreshState(activeSessionId)
      } catch (error) {
        dispatch({
          type: "error",
          message:
            error instanceof Error ? error.message : "Failed to switch permission mode",
        })
      }
    },
    [activeSessionId, refreshState],
  )

  return {
    sessions,
    session: activeSession,
    state,
    eventWindowLimited:
      Boolean(activeSessionId) &&
      eventWindow?.sessionId === activeSessionId &&
      eventWindow.limited,
    streamStatus,
    mode: sessionMode,
    setMode,
    permissionMode,
    setPermissionMode,
    setActiveSessionId,
    refreshSessions,
    refreshState,
    send,
    interrupt,
    decideAction,
  }
}

function mergeSessionList(
  sessions: AgentRuntimeSession[],
  session: AgentRuntimeSession,
) {
  const exists = sessions.some((item) => item.id === session.id)
  if (!exists) return [session, ...sessions]
  return sessions.map((item) => (item.id === session.id ? session : item))
}

function mergeFetchedSessions(
  current: AgentRuntimeSession[],
  fetched: AgentRuntimeSession[],
) {
  const currentById = new Map(current.map((session) => [session.id, session]))
  return fetched.map((session) => {
    const existing = currentById.get(session.id)
    if (!existing) return session
    if (!session.title && existing.title && timestamp(existing.updated_at) > timestamp(session.updated_at)) {
      return { ...session, title: existing.title }
    }
    return session
  })
}

function emitRuntimeSessionUpdated(session: AgentRuntimeSession) {
  if (!session.project_id) return
  emitAgentSessionUpdated({
    id: session.id,
    project_id: session.project_id,
    title: session.title,
    created_at: session.created_at,
    updated_at: session.updated_at,
  })
}

function readDraftPermissionMode(): AgentPermissionMode {
  if (typeof window === "undefined") return DEFAULT_PERMISSION_MODE
  const stored = window.localStorage.getItem(DRAFT_PERMISSION_MODE_STORAGE_KEY)
  return isPermissionMode(stored) ? stored : DEFAULT_PERMISSION_MODE
}

function writeDraftPermissionMode(mode: AgentPermissionMode) {
  if (typeof window === "undefined") return
  window.localStorage.setItem(DRAFT_PERMISSION_MODE_STORAGE_KEY, mode)
}

function isPermissionMode(value: unknown): value is AgentPermissionMode {
  return value === "ask_each_action" || value === "guarded_auto" || value === "bypass"
}

function timestamp(value?: string | null) {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}
