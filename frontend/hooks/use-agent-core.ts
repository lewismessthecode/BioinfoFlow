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
} from "@/lib/agent-core"
import type {
  AgentCoreAction,
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreSession,
  AgentCoreTurn,
} from "@/lib/agent-core"

export type AgentCoreHookStatus = "idle" | "running" | "error"

export function useAgentCore(projectId?: string) {
  const [sessions, setSessions] = useState<AgentCoreSession[]>([])
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null)
  const [turns, setTurns] = useState<AgentCoreTurn[]>([])
  const [events, setEvents] = useState<AgentCoreEvent[]>([])
  const [artifactsByTurn, setArtifactsByTurn] = useState<
    Map<string, AgentCoreArtifact[]>
  >(new Map())
  const [proposedMemories, setProposedMemories] = useState<AgentCoreMemory[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [status, setStatus] = useState<AgentCoreHookStatus>("idle")
  const [error, setError] = useState<Error | null>(null)

  const activeSession = useMemo(
    () => sessions.find((session) => session.id === activeSessionId) ?? null,
    [activeSessionId, sessions],
  )

  const clearTurnState = useCallback(() => {
    setTurns([])
    setEvents([])
    setArtifactsByTurn(new Map())
  }, [])

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
      setActiveSessionId((current) =>
        nextSessions.some((session) => session.id === current)
          ? current
          : nextSessions[0]?.id ?? null,
      )
      await refreshMemories()
    } catch (caught) {
      setError(caught instanceof Error ? caught : new Error("Failed to load AgentCore sessions"))
      setStatus("error")
    } finally {
      setIsLoading(false)
    }
  }, [clearTurnState, projectId, refreshMemories])

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
      permissionMode: "guarded_auto",
      automationMode: "assisted",
    })
    setSessions((current) => [created, ...current])
    setActiveSessionId(created.id)
    return created
  }, [activeSession, projectId])

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

  return {
    sessions,
    activeSession,
    activeSessionId,
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
    sendTurn,
    approveAction,
    rejectAction,
    acceptMemory,
    rejectMemory,
  }
}
