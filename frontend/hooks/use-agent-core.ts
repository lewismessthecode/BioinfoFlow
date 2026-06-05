"use client"

import { useCallback, useEffect, useMemo, useState } from "react"

import {
  acceptAgentMemory,
  createAgentSession,
  createAgentTurn,
  decideAgentAction,
  listAgentSessions,
  listAgentMemories,
  listAgentTurnArtifacts,
  listAgentTurnEvents,
  listAgentTurns,
  rejectAgentMemory,
  updateAgentSession,
  type UpdateAgentSessionInput,
} from "@/lib/agent-core"
import type {
  AgentCoreAction,
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreSession,
  AgentCoreTurn,
  AgentPermissionMode,
} from "@/lib/agent-core"
import {
  emitAgentSessionUpdated,
  getStoredDraftModelProfileId,
  getStoredDraftPermissionMode,
  setStoredDraftModelProfileId,
  setStoredDraftPermissionMode,
} from "@/lib/agent-core/session-storage"

export type AgentCoreHookStatus = "idle" | "running" | "error"

type UseAgentCoreOptions = {
  activeSessionId?: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
}

const DEFAULT_PERMISSION_MODE: AgentPermissionMode = "guarded_auto"

export function useAgentCore(projectId?: string, options: UseAgentCoreOptions = {}) {
  const isControlled = Object.prototype.hasOwnProperty.call(options, "activeSessionId")
  const onActiveSessionIdChange = options.onActiveSessionIdChange
  const controlledActiveSessionId =
    options.activeSessionId && options.activeSessionId.length > 0
      ? options.activeSessionId
      : null
  const [sessions, setSessions] = useState<AgentCoreSession[]>([])
  const [uncontrolledActiveSessionId, setUncontrolledActiveSessionId] =
    useState<string | null>(null)
  const [draftPermissionMode, setDraftPermissionMode] = useState<AgentPermissionMode>(
    DEFAULT_PERMISSION_MODE,
  )
  const [draftModelProfileId, setDraftModelProfileId] = useState<string | null>(null)
  const [turns, setTurns] = useState<AgentCoreTurn[]>([])
  const [events, setEvents] = useState<AgentCoreEvent[]>([])
  const [artifactsByTurn, setArtifactsByTurn] = useState<
    Map<string, AgentCoreArtifact[]>
  >(new Map())
  const [proposedMemories, setProposedMemories] = useState<AgentCoreMemory[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [status, setStatus] = useState<AgentCoreHookStatus>("idle")
  const [error, setError] = useState<Error | null>(null)
  const activeSessionId = isControlled
    ? controlledActiveSessionId
    : uncontrolledActiveSessionId

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  )
  const activePermissionMode = activeSession?.permission_mode ?? draftPermissionMode
  const activeModelProfileId =
    activeSession?.default_model_profile_id ?? draftModelProfileId

  const setActiveSessionId = useCallback(
    (sessionId: string | null) => {
      if (isControlled) {
        onActiveSessionIdChange?.(sessionId ?? "")
        return
      }
      setUncontrolledActiveSessionId(sessionId)
    },
    [isControlled, onActiveSessionIdChange],
  )

  const clearTurnState = useCallback(() => {
    setTurns([])
    setEvents([])
    setArtifactsByTurn(new Map())
  }, [])

  useEffect(() => {
    if (!projectId) {
      setDraftPermissionMode(DEFAULT_PERMISSION_MODE)
      setDraftModelProfileId(null)
      return
    }
    setDraftPermissionMode(
      getStoredDraftPermissionMode(projectId) ?? DEFAULT_PERMISSION_MODE,
    )
    setDraftModelProfileId(getStoredDraftModelProfileId(projectId))
  }, [projectId])

  const refreshMemories = useCallback(async () => {
    if (!projectId) {
      setProposedMemories([])
      return []
    }

    const nextMemories = await listAgentMemories({
      projectId,
      status: "proposed",
    })
    setProposedMemories(nextMemories)
    return nextMemories
  }, [projectId])

  const refreshSessions = useCallback(async () => {
    if (!projectId) {
      setSessions([])
      setActiveSessionId(null)
      clearTurnState()
      setProposedMemories([])
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    setError(null)
    try {
      const nextSessions = await listAgentSessions(projectId)
      setSessions(nextSessions)
      if (isControlled) {
        if (
          controlledActiveSessionId &&
          !nextSessions.some((session) => session.id === controlledActiveSessionId)
        ) {
          setActiveSessionId(null)
        }
      } else {
        setUncontrolledActiveSessionId((current) =>
          nextSessions.some((session) => session.id === current)
            ? current
            : nextSessions[0]?.id ?? null,
        )
      }
      await refreshMemories()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Failed to load AgentCore sessions"))
      setStatus("error")
    } finally {
      setIsLoading(false)
    }
  }, [
    clearTurnState,
    controlledActiveSessionId,
    isControlled,
    projectId,
    refreshMemories,
    setActiveSessionId,
  ])

  useEffect(() => {
    void refreshSessions()
  }, [refreshSessions])

  const refreshTurns = useCallback(
    async (sessionId: string) => {
      const nextTurns = await listAgentTurns(sessionId)
      setTurns(nextTurns)
      const ledgers = await Promise.all(
        nextTurns.map(async (turn) => {
          const [turnEvents, turnArtifacts] = await Promise.all([
            listAgentTurnEvents(turn.id),
            listAgentTurnArtifacts(turn.id),
          ])
          return { turn, turnEvents, turnArtifacts }
        }),
      )

      setEvents(ledgers.flatMap((ledger) => ledger.turnEvents))
      setArtifactsByTurn(
        new Map(
          ledgers.map((ledger) => [
            ledger.turn.id,
            ledger.turnArtifacts,
          ]),
        ),
      )
      return nextTurns
    },
    [],
  )

  useEffect(() => {
    if (!activeSessionId) {
      clearTurnState()
      return
    }

    void refreshTurns(activeSessionId).catch((caught) => {
      setStatus("error")
      setError(caught instanceof Error ? caught : new Error("Failed to load AgentCore turns"))
    })
  }, [activeSessionId, clearTurnState, refreshTurns])

  const ensureSession = useCallback(async () => {
    if (!projectId) throw new Error("Project is required to create an AgentCore session")
    if (activeSession) return activeSession
    const created = await createAgentSession({
      projectId,
      title: "New analysis",
      permissionMode: draftPermissionMode,
      automationMode: "assisted",
      defaultModelProfileId: draftModelProfileId ?? undefined,
    })
    setSessions((current) => [created, ...current])
    setActiveSessionId(created.id)
    emitAgentSessionUpdated(created)
    return created
  }, [
    activeSession,
    draftModelProfileId,
    draftPermissionMode,
    projectId,
    setActiveSessionId,
  ])

  const sendTurn = useCallback(
    async (inputText: string) => {
      const text = inputText.trim()
      if (!text) return null

      setStatus("running")
      setError(null)
      try {
        const session = await ensureSession()
        const turn = await createAgentTurn({
          sessionId: session.id,
          inputText: text,
        })
        setTurns((current) => [...current, turn])
        const [turnEvents, turnArtifacts] = await Promise.all([
          listAgentTurnEvents(turn.id),
          listAgentTurnArtifacts(turn.id),
        ])
        setEvents((current) => [...current, ...turnEvents])
        setArtifactsByTurn((current) => {
          const next = new Map(current)
          next.set(turn.id, turnArtifacts)
          return next
        })
        await refreshMemories()
        setStatus("idle")
        return turn
      } catch (caught) {
        setStatus("error")
        setError(caught instanceof Error ? caught : new Error("Failed to send AgentCore turn"))
        return null
      }
    },
    [ensureSession, refreshMemories],
  )

  const recordActionDecision = useCallback(
    async (
      actionId: string,
      decision: "approve" | "reject",
    ): Promise<AgentCoreAction | null> => {
      setStatus("running")
      setError(null)
      try {
        const action = await decideAgentAction(actionId, decision)
        if (activeSessionId) await refreshTurns(activeSessionId)
        setStatus("idle")
        return action
      } catch (caught) {
        setStatus("error")
        setError(caught instanceof Error ? caught : new Error("Failed to decide AgentCore action"))
        return null
      }
    },
    [activeSessionId, refreshTurns],
  )

  const approveAction = useCallback(
    (actionId: string) => recordActionDecision(actionId, "approve"),
    [recordActionDecision],
  )

  const rejectAction = useCallback(
    (actionId: string) => recordActionDecision(actionId, "reject"),
    [recordActionDecision],
  )

  const acceptMemory = useCallback(async (memoryId: string) => {
    setError(null)
    try {
      const memory = await acceptAgentMemory(memoryId)
      setProposedMemories((current) =>
        current.filter((item) => item.id !== memoryId),
      )
      return memory
    } catch (caught) {
      setStatus("error")
      setError(caught instanceof Error ? caught : new Error("Failed to accept AgentCore memory"))
      return null
    }
  }, [])

  const rejectMemory = useCallback(async (memoryId: string) => {
    setError(null)
    try {
      const memory = await rejectAgentMemory(memoryId)
      setProposedMemories((current) =>
        current.filter((item) => item.id !== memoryId),
      )
      return memory
    } catch (caught) {
      setStatus("error")
      setError(caught instanceof Error ? caught : new Error("Failed to reject AgentCore memory"))
      return null
    }
  }, [])

  const updateSessionSettings = useCallback(
    async (updates: UpdateAgentSessionInput) => {
      if (activeSession) {
        setError(null)
        try {
          const updated = await updateAgentSession(activeSession.id, updates)
          setSessions((current) =>
            current.map((session) =>
              session.id === updated.id ? updated : session,
            ),
          )
          emitAgentSessionUpdated(updated)
          return updated
        } catch (caught) {
          setStatus("error")
          setError(
            caught instanceof Error
              ? caught
              : new Error("Failed to update AgentCore session"),
          )
          return null
        }
      }

      if (updates.permissionMode) {
        setDraftPermissionMode(updates.permissionMode)
        if (projectId) {
          setStoredDraftPermissionMode(projectId, updates.permissionMode)
        }
      }
      if (Object.prototype.hasOwnProperty.call(updates, "defaultModelProfileId")) {
        const profileId = updates.defaultModelProfileId ?? null
        setDraftModelProfileId(profileId)
        if (projectId) {
          setStoredDraftModelProfileId(projectId, profileId)
        }
      }
      return null
    },
    [activeSession, projectId],
  )

  return {
    sessions,
    activeSession,
    activeSessionId,
    activePermissionMode,
    activeModelProfileId,
    turns,
    events,
    artifactsByTurn,
    proposedMemories,
    isLoading,
    status,
    error,
    refreshSessions,
    refreshTurns,
    setActiveSessionId,
    updateSessionSettings,
    sendTurn,
    approveAction,
    rejectAction,
    acceptMemory,
    rejectMemory,
  }
}
