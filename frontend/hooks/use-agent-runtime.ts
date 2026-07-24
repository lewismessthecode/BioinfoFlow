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
  steerAgentRuntimeTurn,
  updateAgentRuntimeSessionMetadata,
  updateAgentRuntimeSessionMode,
  updateAgentRuntimeSessionPermissionMode,
  type AgentActionDecision,
  type AgentAnswer,
  type AgentExecutionScope,
  type AgentExecutionTarget,
  type AgentMode,
  type AgentModelSelection,
  type AgentPendingReconciliation,
  type AgentPendingStrategy,
  type AgentPermissionMode,
  type AgentRuntimeInputPart,
  type AgentRuntimeSession,
} from "@/lib/agent-runtime"
import { emitAgentSessionUpdated } from "@/lib/agent-core/session-storage"
import {
  mergeSessionByPolicyVersion,
  restorePermissionPolicy,
  sessionPolicyVersion,
} from "@/lib/agent-runtime/session-policy"
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

export type AgentPermissionUpdateState = {
  status: "idle" | "pending" | "success" | "error"
  mode: AgentPermissionMode | null
  pendingStrategy: AgentPendingStrategy | null
  reconciliation: AgentPendingReconciliation | null
  error: string | null
}

type PermissionUpdateRequest = {
  sequence: number
  draftSequence: number
  sessionId: string | null
  basePolicyVersion: number
  mode: AgentPermissionMode
  pendingStrategy: AgentPendingStrategy
  rollbackSession: AgentRuntimeSession | null
}

const DRAFT_PERMISSION_MODE_STORAGE_KEY = "bioinfoflow.agentRuntime.permissionMode:v2"
const LEGACY_DRAFT_PERMISSION_MODE_STORAGE_KEY = "bioinfoflow.agentRuntime.permissionMode"
const DEFAULT_PERMISSION_MODE: AgentPermissionMode = "guarded_auto"
const INITIAL_PERMISSION_UPDATE_STATE: AgentPermissionUpdateState = {
  status: "idle",
  mode: null,
  pendingStrategy: null,
  reconciliation: null,
  error: null,
}
const INTERRUPTIBLE_TURN_STATUSES = new Set([
  "queued",
  "running",
  "waiting_user",
  "waiting_approval",
])

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
  const [permissionUpdate, setPermissionUpdate] =
    useState<AgentPermissionUpdateState>(INITIAL_PERMISSION_UPDATE_STATE)
  const streamCursorRef = useRef(0)
  const sessionListRefreshSequenceRef = useRef(0)
  const stateRefreshSequenceRef = useRef(0)
  const confirmedDraftPermissionModeRef = useRef(draftPermissionMode)
  const confirmedStorageValueRef = useRef(readStoredDraftPermissionMode())
  const confirmedDraftSequenceRef = useRef(0)
  const confirmedSessionsRef = useRef(new Map<string, AgentRuntimeSession>())
  const latestSessionsRef = useRef<AgentRuntimeSession[]>([])
  const permissionUpdateSequenceRef = useRef(0)
  const permissionDraftSequenceRef = useRef(0)
  const permissionUpdateTailRef = useRef<Promise<unknown>>(Promise.resolve())
  const permissionUpdatePromisesRef = useRef(
    new Map<string, Promise<AgentRuntimeSession | null>>(),
  )
  const lastPermissionUpdateRequestRef = useRef<PermissionUpdateRequest | null>(null)
  const pendingPermissionIntentRef = useRef<PermissionUpdateRequest | null>(null)
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
  const activeSessionRef = useRef(activeSession)
  activeSessionRef.current = activeSession
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

  const updateSessions = useCallback(
    (updater: (current: AgentRuntimeSession[]) => AgentRuntimeSession[]) => {
      const next = updater(latestSessionsRef.current)
      latestSessionsRef.current = next
      setSessions(next)
    },
    [],
  )

  const refreshSessions = useCallback(async () => {
    const sequence = sessionListRefreshSequenceRef.current + 1
    sessionListRefreshSequenceRef.current = sequence
    const requestedActiveSessionId = activeSessionIdRef.current
    if (!requestedActiveSessionId) {
      dispatch({ type: "loading" })
    }
    try {
      const nextSessions = await listAgentRuntimeSessions(projectId)
      if (sessionListRefreshSequenceRef.current !== sequence) return
      if (activeSessionIdRef.current !== requestedActiveSessionId) return
      const pendingIntent = pendingPermissionIntentRef.current
      for (const session of nextSessions) {
        adoptPendingPermissionBaseline(pendingIntent, session)
        rememberConfirmedSession(confirmedSessionsRef.current, session)
      }
      updateSessions((current) =>
        applyPendingPermissionIntent(
          mergeFetchedSessions(current, nextSessions),
          pendingIntent,
        ),
      )
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
      if (sessionListRefreshSequenceRef.current !== sequence) return
      if (activeSessionIdRef.current !== requestedActiveSessionId) return
      if (!requestedActiveSessionId) {
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Failed to load sessions",
        })
      }
    }
  }, [activeSessionId, isControlledDraft, projectId, setActiveSessionId, updateSessions])

  useEffect(() => {
    const previousSessionId = activeSessionIdRef.current
    activeSessionIdRef.current = activeSessionId
    if (previousSessionId === activeSessionId) return
    permissionUpdateSequenceRef.current += 1
    const request = lastPermissionUpdateRequestRef.current
    if (request?.sessionId !== activeSessionId) {
      lastPermissionUpdateRequestRef.current = null
      pendingPermissionIntentRef.current = null
      setPermissionUpdate(INITIAL_PERMISSION_UPDATE_STATE)
    }
  }, [activeSessionId])

  useEffect(() => {
    if (!activeSession) return
    if (permissionUpdate.status === "pending") return
    const confirmed = confirmedSessionsRef.current.get(activeSession.id)
    if (isSessionPolicyNewer(activeSession, confirmed)) {
      confirmedSessionsRef.current.set(activeSession.id, activeSession)
    }
  }, [activeSession, permissionUpdate.status])

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
    const sequence = stateRefreshSequenceRef.current + 1
    stateRefreshSequenceRef.current = sequence
    dispatch({ type: "loading" })
    try {
      const payload = await getAgentRuntimeState(sessionId, {
        eventView: "public",
      })
      if (activeSessionIdRef.current !== sessionId) return
      if (stateRefreshSequenceRef.current !== sequence) return
      setEventWindow({
        sessionId,
        limited: false,
      })
      const pendingIntent = pendingPermissionIntentRef.current
      adoptPendingPermissionBaseline(pendingIntent, payload.session)
      rememberConfirmedSession(confirmedSessionsRef.current, payload.session)
      const loadedSession = sessionWithPendingPermissionIntent(
        payload.session,
        pendingIntent,
      )
      updateSessions((current) => mergeSessionList(current, loadedSession))
      emitRuntimeSessionUpdated(payload.session)
      dispatch({ type: "state.loaded", payload: { ...payload, session: loadedSession } })
    } catch (error) {
      if (activeSessionIdRef.current !== sessionId) return
      if (stateRefreshSequenceRef.current !== sequence) return
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Failed to load agent state",
      })
    }
  }, [updateSessions])

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
      },
      onError: () => {
        setStreamSignal({ sessionId: activeSessionId, status: "reconnecting" })
      },
      onEvent: (event) => {
        setStreamSignal({ sessionId: activeSessionId, status: "connected" })
        streamCursorRef.current = Math.max(streamCursorRef.current, event.seq)
        dispatch({ type: "event.append", event })
        if (eventTriggersStateRefresh(event.type)) {
          void refreshState(activeSessionId)
        }
      },
    })
  }, [activeSessionId, isLiveRuntime, refreshState, streamCanStart])

  const ensureSessionWithMetadata = useCallback(
    async (
      modelSelection?: AgentModelSelection | null,
      metadata?: Record<string, unknown>,
      executionTarget?: AgentExecutionTarget | null,
      executionScope?: AgentExecutionScope,
    ) => {
      if (activeSession) return activeSession
      const created = await createAgentRuntimeSession({
        projectId: projectId || null,
        permissionMode: draftPermissionMode,
        mode: draftMode,
        modelSelection,
        executionTarget,
        executionScope,
        metadata,
      })
      updateSessions((current) => [created, ...current])
      activeSessionIdRef.current = created.id
      setActiveSessionId(created.id)
      dispatch({ type: "session.selected", session: created })
      return created
    },
    [
      activeSession,
      draftMode,
      draftPermissionMode,
      projectId,
      setActiveSessionId,
      updateSessions,
    ],
  )

  const ensureSessionExecutionMetadata = useCallback(
    async (
      session: AgentRuntimeSession,
      {
        remoteConnectionId,
        executionScope,
        executionTarget,
        syncExecutionTarget,
      }: {
        remoteConnectionId?: string | null
        executionScope?: AgentExecutionScope | null
        executionTarget?: AgentExecutionTarget | null
        syncExecutionTarget: boolean
      },
    ) => {
      const hasRemoteConnectionOverride = remoteConnectionId !== undefined
      const hasExecutionScope = executionScope !== undefined
      if (!hasRemoteConnectionOverride && !hasExecutionScope && !syncExecutionTarget) {
        return session
      }

      const metadata = { ...(session.metadata ?? {}) }
      if (hasRemoteConnectionOverride) {
        if (remoteConnectionId) {
          metadata.remote_connection_id = remoteConnectionId
        } else {
          delete metadata.remote_connection_id
        }
      }

      if (syncExecutionTarget) {
        const targetRemoteConnectionId =
          remoteConnectionIdFromExecutionTarget(executionTarget)
        if (targetRemoteConnectionId) {
          metadata.remote_connection_id = targetRemoteConnectionId
        } else if (!remoteConnectionId) {
          delete metadata.remote_connection_id
        }
        if (executionTarget === null) {
          delete metadata.execution_target
        }
      }

      const updated = await updateAgentRuntimeSessionMetadata(
        session.id,
        Object.keys(metadata).length ? metadata : null,
        syncExecutionTarget ? executionTarget : undefined,
        hasExecutionScope ? executionScope : undefined,
      )
      updateSessions((current) => mergeSessionList(current, updated))
      if (activeSessionIdRef.current === updated.id) {
        dispatch({ type: "session.selected", session: updated })
      }
      emitRuntimeSessionUpdated(updated)
      return updated
    },
    [updateSessions],
  )

  const send = useCallback(
    async (
      inputText: string,
      options?: {
        modelSelection?: AgentModelSelection | null
        inputParts?: AgentRuntimeInputPart[] | null
        activeSkillNames?: string[] | null
        remoteConnectionId?: string | null
        executionScope?: AgentExecutionScope | null
        metadata?: Record<string, unknown> | null
      },
    ) => {
      const text = inputText.trim()
      const hasStructuredInput = Boolean(
        options?.inputParts?.some((part) =>
          "type" in part ? part.type !== "text" : "kind" in part,
        ),
      )
      if (!text && !hasStructuredInput) return null
      dispatch({ type: "loading" })
      try {
        const remoteConnectionId = Object.hasOwn(options ?? {}, "remoteConnectionId")
          ? options?.remoteConnectionId
          : undefined
        const executionScope = options?.executionScope ?? undefined
        const scopeExecutionTarget =
          remoteConnectionId === undefined
            ? executionTargetForExecutionScope(executionScope)
            : undefined
        const syncExecutionTarget =
          remoteConnectionId !== undefined || executionScope !== undefined
        const executionTarget =
          remoteConnectionId !== undefined
            ? executionTargetForRemoteConnectionId(remoteConnectionId)
            : scopeExecutionTarget
        const metadata = metadataForExecutionRequest({
          remoteConnectionId,
          executionTarget,
        })
        const baseSession = await ensureSessionWithMetadata(
          options?.modelSelection,
          metadata,
          executionTarget,
          executionScope,
        )
        const session = activeSession
          ? await ensureSessionExecutionMetadata(baseSession, {
              remoteConnectionId,
              executionScope,
              executionTarget,
              syncExecutionTarget,
            })
          : baseSession
        const turn = await createAgentRuntimeTurn({
          sessionId: session.id,
          inputText: text,
          inputParts: options?.inputParts,
          activeSkillNames: options?.activeSkillNames,
          modelSelection: options?.modelSelection,
          executionTarget,
          executionScope,
          metadata: metadataWithClientTimeZone(options?.metadata),
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
    [
      activeSession,
      ensureSessionExecutionMetadata,
      ensureSessionWithMetadata,
      refreshState,
    ],
  )

  const interrupt = useCallback(async () => {
    const running = [...state.turns]
      .reverse()
      .find((turn) => INTERRUPTIBLE_TURN_STATUSES.has(turn.status))
    if (!running) return null
    const turn = await interruptAgentRuntimeTurn(running.id)
    dispatch({ type: "turn.upsert", turn })
    return turn
  }, [state.turns])

  const steer = useCallback(
    async (
      text: string,
      options?: {
        inputParts?: AgentRuntimeInputPart[] | null
        activeSkillNames?: string[] | null
        metadata?: Record<string, unknown> | null
      },
    ) => {
      const running = [...state.turns]
        .reverse()
        .find((turn) => INTERRUPTIBLE_TURN_STATUSES.has(turn.status))
      if (!running) return null
      try {
        const outcome = await steerAgentRuntimeTurn(running.id, {
          inputText: text,
          inputParts: options?.inputParts,
          activeSkillNames: options?.activeSkillNames,
          metadata: options?.metadata,
        })
        if (outcome.kind === "accepted") {
          await refreshState(running.session_id)
        }
        return outcome
      } catch (error) {
        dispatch({
          type: "error",
          message: error instanceof Error ? error.message : "Failed to guide response",
        })
        return null
      }
    },
    [refreshState, state.turns],
  )

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
        throw error
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
    (
      mode: AgentPermissionMode,
      pendingStrategy: AgentPendingStrategy = "future_only",
    ): Promise<AgentRuntimeSession | null> => {
      const sessionId = activeSessionIdRef.current
      const requestKey = `${sessionId ?? "draft"}:${mode}:${pendingStrategy}`
      const duplicate = permissionUpdatePromisesRef.current.get(requestKey)
      if (duplicate) return duplicate

      const sequence = permissionUpdateSequenceRef.current + 1
      permissionUpdateSequenceRef.current = sequence
      const draftSequence = permissionDraftSequenceRef.current + 1
      permissionDraftSequenceRef.current = draftSequence
      const rollbackSession = sessionId
        ? latestSessionsRef.current.find((item) => item.id === sessionId) ??
          (activeSessionRef.current?.id === sessionId ? activeSessionRef.current : null)
        : null
      const request: PermissionUpdateRequest = {
        sequence,
        draftSequence,
        sessionId,
        basePolicyVersion: sessionPolicyVersion(rollbackSession ?? undefined),
        mode,
        pendingStrategy,
        rollbackSession,
      }
      if (
        rollbackSession &&
        !confirmedSessionsRef.current.has(rollbackSession.id)
      ) {
        confirmedSessionsRef.current.set(rollbackSession.id, rollbackSession)
      }
      lastPermissionUpdateRequestRef.current = request
      pendingPermissionIntentRef.current = request

      setDraftPermissionModeState(mode)
      writeDraftPermissionMode(mode)
      if (sessionId) {
        updateSessions((current) =>
          optimisticPermissionSessions(current, rollbackSession, sessionId, mode),
        )
      }
      setPermissionUpdate({
        status: sessionId ? "pending" : "success",
        mode,
        pendingStrategy,
        reconciliation: null,
        error: null,
      })

      if (!sessionId) {
        pendingPermissionIntentRef.current = null
        confirmedDraftPermissionModeRef.current = mode
        confirmedStorageValueRef.current = mode
        confirmedDraftSequenceRef.current = draftSequence
        return Promise.resolve(null)
      }

      const execute = async (): Promise<AgentRuntimeSession | null> => {
        try {
          const updated = await updateAgentRuntimeSessionPermissionMode(
            sessionId,
            mode,
            pendingStrategy,
          )
          const latestSession = latestSessionsRef.current.find(
            (item) => item.id === sessionId,
          )
          if (!isSessionPolicyNewerOrEqual(updated, latestSession)) {
            throw new Error("Permission update was superseded by a newer policy version")
          }
          const confirmed = confirmedSessionsRef.current.get(sessionId)
          if (!isSessionPolicyNewerOrEqual(updated, confirmed)) {
            throw new Error("Permission update was superseded by a newer policy version")
          }
          confirmedSessionsRef.current.set(sessionId, updated)
          const pendingIntent = pendingPermissionIntentRef.current
          if (
            pendingIntent?.sessionId === sessionId &&
            pendingIntent.sequence > sequence
          ) {
            pendingIntent.basePolicyVersion = Math.max(
              pendingIntent.basePolicyVersion,
              sessionPolicyVersion(updated),
            )
          }
          updateSessions((current) =>
            applyPendingPermissionIntent(
              mergeSessionList(current, updated),
              pendingPermissionIntentRef.current,
            ),
          )
          if (draftSequence >= confirmedDraftSequenceRef.current) {
            confirmedDraftPermissionModeRef.current = mode
            confirmedStorageValueRef.current = mode
            confirmedDraftSequenceRef.current = draftSequence
          }

          if (
            permissionUpdateSequenceRef.current === sequence &&
            activeSessionIdRef.current === sessionId
          ) {
            pendingPermissionIntentRef.current = null
            setPermissionUpdate({
              status: "success",
              mode,
              pendingStrategy,
              reconciliation: updated.pending_reconciliation ?? null,
              error: null,
            })
          }
          return updated
        } catch (error) {
          const message =
            error instanceof Error ? error.message : "Failed to switch permission mode"
          if (permissionDraftSequenceRef.current === draftSequence) {
            setDraftPermissionModeState(confirmedDraftPermissionModeRef.current)
            restoreStoredDraftPermissionMode(confirmedStorageValueRef.current)
          }
          const pendingIntent = pendingPermissionIntentRef.current
          const supersededByNewerIntent =
            pendingIntent?.sessionId === sessionId && pendingIntent.sequence > sequence
          const policySnapshot = newestPolicySnapshot(
            request.rollbackSession,
            confirmedSessionsRef.current.get(sessionId),
          )
          if (!supersededByNewerIntent && policySnapshot) {
            updateSessions((current) =>
              current.map((item) =>
                item.id === sessionId
                  ? restorePermissionPolicy(item, policySnapshot)
                  : item,
              ),
            )
            if (activeSessionIdRef.current === sessionId) {
              dispatch({ type: "session.permission_restored", session: policySnapshot })
            }
          }
          if (
            permissionUpdateSequenceRef.current === sequence &&
            activeSessionIdRef.current === sessionId
          ) {
            pendingPermissionIntentRef.current = null
            setPermissionUpdate({
              status: "error",
              mode,
              pendingStrategy,
              reconciliation: null,
              error: message,
            })
          }
          return null
        }
      }

      const promise = permissionUpdateTailRef.current.then(execute, execute)
      permissionUpdateTailRef.current = promise.then(
        () => undefined,
        () => undefined,
      )
      permissionUpdatePromisesRef.current.set(requestKey, promise)
      void promise.finally(() => {
        if (permissionUpdatePromisesRef.current.get(requestKey) === promise) {
          permissionUpdatePromisesRef.current.delete(requestKey)
        }
      })
      return promise
    },
    [updateSessions],
  )

  const retryPermissionModeUpdate = useCallback(() => {
    const request = lastPermissionUpdateRequestRef.current
    if (!request) return Promise.resolve(null)
    if (request.sessionId !== activeSessionIdRef.current) {
      lastPermissionUpdateRequestRef.current = null
      return Promise.resolve(null)
    }
    return setPermissionMode(request.mode, request.pendingStrategy)
  }, [setPermissionMode])

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
    permissionUpdate,
    retryPermissionModeUpdate,
    setActiveSessionId,
    refreshSessions,
    refreshState,
    ensureSession: ensureSessionWithMetadata,
    send,
    steer,
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
  return sessions.map((item) =>
    item.id === session.id ? mergeSessionByPolicyVersion(item, session) : item,
  )
}

function optimisticPermissionSessions(
  sessions: AgentRuntimeSession[],
  rollbackSession: AgentRuntimeSession | null,
  sessionId: string,
  mode: AgentPermissionMode,
) {
  if (sessions.some((item) => item.id === sessionId)) {
    return sessions.map((item) =>
      item.id === sessionId ? { ...item, permission_mode: mode } : item,
    )
  }
  return rollbackSession
    ? [{ ...rollbackSession, permission_mode: mode }, ...sessions]
    : sessions
}

function newestPolicySnapshot(
  first: AgentRuntimeSession | null,
  second?: AgentRuntimeSession,
) {
  if (!first) return second ?? null
  if (!second) return first
  return sessionPolicyVersion(second) >= sessionPolicyVersion(first) ? second : first
}

function rememberConfirmedSession(
  confirmedSessions: Map<string, AgentRuntimeSession>,
  session: AgentRuntimeSession,
) {
  const confirmed = confirmedSessions.get(session.id)
  if (isSessionPolicyNewerOrEqual(session, confirmed)) {
    confirmedSessions.set(session.id, session)
  }
}

function adoptPendingPermissionBaseline(
  intent: PermissionUpdateRequest | null,
  session: AgentRuntimeSession,
) {
  if (!intent?.sessionId || intent.sessionId !== session.id) return
  if (intent.rollbackSession) return
  intent.rollbackSession = session
  intent.basePolicyVersion = sessionPolicyVersion(session)
}

function applyPendingPermissionIntent(
  sessions: AgentRuntimeSession[],
  intent: PermissionUpdateRequest | null,
) {
  if (!intent?.sessionId) return sessions
  return sessions.map((session) => sessionWithPendingPermissionIntent(session, intent))
}

function sessionWithPendingPermissionIntent(
  session: AgentRuntimeSession,
  intent: PermissionUpdateRequest | null,
) {
  if (!intent?.sessionId || session.id !== intent.sessionId) return session
  if (sessionPolicyVersion(session) > intent.basePolicyVersion) return session
  return { ...session, permission_mode: intent.mode }
}

function mergeFetchedSessions(
  current: AgentRuntimeSession[],
  fetched: AgentRuntimeSession[],
) {
  const currentById = new Map(current.map((session) => [session.id, session]))
  return fetched.map((session) => {
    const existing = currentById.get(session.id)
    if (!existing) return session
    const merged = mergeSessionByPolicyVersion(existing, session)
    if (!session.title && existing.title && timestamp(existing.updated_at) > timestamp(session.updated_at)) {
      return { ...merged, title: existing.title }
    }
    return merged
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
  const stored = readStoredDraftPermissionMode()
  if (isPermissionMode(stored)) return stored
  const legacy = safeStorageGet(LEGACY_DRAFT_PERMISSION_MODE_STORAGE_KEY)
  return isPermissionMode(legacy) ? legacy : DEFAULT_PERMISSION_MODE
}

function writeDraftPermissionMode(mode: AgentPermissionMode) {
  if (typeof window === "undefined") return
  try {
    window.localStorage.setItem(DRAFT_PERMISSION_MODE_STORAGE_KEY, mode)
  } catch {
    // Storage can be unavailable in private browsing or restricted embeds.
  }
}

function readStoredDraftPermissionMode() {
  return safeStorageGet(DRAFT_PERMISSION_MODE_STORAGE_KEY)
}

function safeStorageGet(key: string) {
  if (typeof window === "undefined") return null
  try {
    return window.localStorage.getItem(key)
  } catch {
    return null
  }
}

function restoreStoredDraftPermissionMode(value: string | null) {
  if (typeof window === "undefined") return
  try {
    if (value === null) {
      window.localStorage.removeItem(DRAFT_PERMISSION_MODE_STORAGE_KEY)
    } else {
      window.localStorage.setItem(DRAFT_PERMISSION_MODE_STORAGE_KEY, value)
    }
  } catch {
    // The in-memory draft still rolls back when browser storage is unavailable.
  }
}

function eventTriggersStateRefresh(type: string) {
  return (
    type === "turn.completed" ||
    type === "turn.failed" ||
    type === "turn.cancelled" ||
    type === "turn.interrupted" ||
    type === "turn.no_progress" ||
    type === "action.waiting_decision"
  )
}

function isPermissionMode(value: unknown): value is AgentPermissionMode {
  return value === "ask_each_action" || value === "guarded_auto" || value === "bypass"
}

function metadataForExecutionRequest({
  remoteConnectionId,
  executionTarget,
}: {
  remoteConnectionId?: string | null
  executionTarget?: AgentExecutionTarget | null
}): Record<string, unknown> | undefined {
  const connectionId =
    remoteConnectionId || remoteConnectionIdFromExecutionTarget(executionTarget)
  return connectionId ? { remote_connection_id: connectionId } : undefined
}

function metadataWithClientTimeZone(
  metadata: Record<string, unknown> | null | undefined,
): Record<string, unknown> | undefined {
  const next = { ...(metadata ?? {}) }
  try {
    const timeZone = Intl.DateTimeFormat().resolvedOptions().timeZone?.trim()
    if (timeZone) next.client_timezone = timeZone
  } catch {
    // The backend falls back to an explicit UTC date when browser locale data
    // is unavailable.
  }
  return Object.keys(next).length ? next : undefined
}

function executionTargetForExecutionScope(
  executionScope: AgentExecutionScope | null | undefined,
): AgentExecutionTarget | null | undefined {
  if (executionScope === undefined) return undefined
  if (!executionScope || executionScope.mode === "auto") return null
  const targets = executionScope.selected_targets ?? []
  if (targets.length !== 1) return null
  const target = targets[0]
  const kind = target.kind ?? target.type
  if (kind === "local") return null
  if (kind !== "remote_ssh") return null
  const remoteConnectionId =
    nonEmptyString(target.remote_connection_id) ?? nonEmptyString(target.connection_id)
  if (!remoteConnectionId) return null
  return {
    kind: "remote_ssh",
    type: "remote_ssh",
    remote_connection_id: remoteConnectionId,
    connection_id: remoteConnectionId,
  }
}

function executionTargetForRemoteConnectionId(
  remoteConnectionId: string | null | undefined,
): AgentExecutionTarget | undefined {
  if (remoteConnectionId === undefined) return undefined
  if (remoteConnectionId) {
    return {
      kind: "remote_ssh",
      type: "remote_ssh",
      remote_connection_id: remoteConnectionId,
      connection_id: remoteConnectionId,
    }
  }
  return { kind: "local", type: "local" }
}

function remoteConnectionIdFromExecutionTarget(
  executionTarget: AgentExecutionTarget | null | undefined,
) {
  if (!executionTarget) return null
  const kind = executionTarget.kind ?? executionTarget.type
  if (kind !== "remote_ssh") return null
  return (
    nonEmptyString(executionTarget.remote_connection_id) ??
    nonEmptyString(executionTarget.connection_id)
  )
}

function nonEmptyString(value: unknown) {
  return typeof value === "string" && value ? value : null
}

function timestamp(value?: string | null) {
  if (!value) return 0
  const parsed = Date.parse(value)
  return Number.isNaN(parsed) ? 0 : parsed
}

function isSessionPolicyNewer(
  candidate: AgentRuntimeSession,
  current?: AgentRuntimeSession,
) {
  if (!current) return true
  return sessionPolicyVersion(candidate) > sessionPolicyVersion(current)
}

function isSessionPolicyNewerOrEqual(
  candidate: AgentRuntimeSession,
  current?: AgentRuntimeSession,
) {
  if (!current) return true
  return sessionPolicyVersion(candidate) >= sessionPolicyVersion(current)
}
