"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import {
  dispatchAgentCommand,
  getAgentSnapshot,
} from "@/lib/agent/client"
import { subscribeAgentEvents } from "@/lib/agent/stream"
import {
  applyAgentEvent,
  initialAgentStoreState,
  type AgentStoreState,
} from "@/lib/agent/store"
import type {
  AgentCommand,
  AgentEvent,
  InputPart,
  InteractionResponse,
  SessionSnapshot,
} from "@/lib/agent/contracts"
import type { AgentConnectionStatus } from "@/lib/agent/stream"

type AgentSessionState = AgentStoreState & {
  connectionStatus: AgentConnectionStatus
  error: Error | null
  isLoading: boolean
  sendMessage: (parts: InputPart[]) => Promise<void>
  steer: (parts: InputPart[]) => Promise<void>
  respond: (
    interactionId: string,
    response: InteractionResponse,
  ) => Promise<void>
  cancel: () => Promise<void>
}

type AgentSessionViewState = {
  sessionId: string
  store: AgentStoreState
  connectionStatus: AgentConnectionStatus
  error: Error | null
  isLoading: boolean
}

export function useAgentSession(sessionId: string): AgentSessionState {
  const [view, setView] = useState<AgentSessionViewState>(() =>
    initialView(sessionId),
  )
  const storeRef = useRef(initialAgentStoreState)
  const generationRef = useRef(0)

  const replaceSnapshot = useCallback(
    (
      expectedGeneration: number,
      expectedSessionId: string,
      snapshot: SessionSnapshot,
    ) => {
      if (generationRef.current !== expectedGeneration) return false
      const next = applyAgentEvent(storeRef.current, {
        type: "snapshot",
        snapshot,
      }).state
      storeRef.current = next
      setView((current) => ({
        ...(current.sessionId === expectedSessionId
          ? current
          : initialView(expectedSessionId)),
        store: next,
        error: null,
        isLoading: false,
      }))
      return true
    },
    [],
  )

  useEffect(() => {
    let active = true
    let snapshotRequest: Promise<boolean> | null = null
    const generation = generationRef.current + 1

    generationRef.current = generation
    storeRef.current = initialAgentStoreState

    const refreshSnapshot = () => {
      if (snapshotRequest) return snapshotRequest
      snapshotRequest = getAgentSnapshot(sessionId)
        .then((snapshot) => {
          if (!active) return false
          return replaceSnapshot(generation, sessionId, snapshot)
        })
        .catch((caught) => {
          if (!active) return false
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            error: asError(caught, "Unable to load agent session"),
          }))
          return false
        })
        .finally(() => {
          snapshotRequest = null
        })
      return snapshotRequest
    }

    const onEvent = (event: AgentEvent) => {
      if (!active) return
      const application = applyAgentEvent(storeRef.current, event)
      if (application.outcome === "needs_snapshot") {
        void refreshSnapshot()
        return
      }
      if (application.outcome === "ignored") return
      storeRef.current = application.state
      setView((current) => {
        const base =
          current.sessionId === sessionId ? current : initialView(sessionId)
        return {
          ...base,
          store: application.state,
          error: event.type === "snapshot" ? null : base.error,
          isLoading: event.type === "snapshot" ? false : base.isLoading,
        }
      })
    }

    const unsubscribe = subscribeAgentEvents({
      sessionId,
      onEvent,
      onConnectionChange: (status) => {
        if (!active) return
        setView((current) => ({
          ...(current.sessionId === sessionId
            ? current
            : initialView(sessionId)),
          connectionStatus: status,
        }))
      },
      onError: () => {
        if (!active) return
        setView((current) => ({
          ...(current.sessionId === sessionId
            ? current
            : initialView(sessionId)),
          error: new Error("Agent event stream disconnected"),
        }))
      },
    })

    return () => {
      active = false
      if (generationRef.current === generation) generationRef.current += 1
      unsubscribe()
    }
  }, [replaceSnapshot, sessionId])

  const runCommand = useCallback(
    async (command: AgentCommand) => {
      const generation = generationRef.current
      setView((current) => ({
        ...(current.sessionId === sessionId
          ? current
          : initialView(sessionId)),
        error: null,
      }))
      try {
        await dispatchAgentCommand(sessionId, command)
      } catch (caught) {
        if (generationRef.current === generation) {
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            error: asError(caught, "Agent command failed"),
          }))
        }
        throw caught
      }
    },
    [sessionId],
  )

  const sendMessage = useCallback(
    (parts: InputPart[]) =>
      runCommand({
        type: "message",
        command_id: createCommandId(),
        parts,
      }),
    [runCommand],
  )

  const steer = useCallback(
    (parts: InputPart[]) =>
      runCommand({
        type: "steer",
        command_id: createCommandId(),
        parts,
      }),
    [runCommand],
  )

  const respond = useCallback(
    (interactionId: string, response: InteractionResponse) =>
      runCommand({
        type: "respond",
        command_id: createCommandId(),
        interaction_id: interactionId,
        response,
      }),
    [runCommand],
  )

  const cancel = useCallback(
    () =>
      runCommand({
        type: "cancel",
        command_id: createCommandId(),
      }),
    [runCommand],
  )

  const currentView =
    view.sessionId === sessionId ? view : initialView(sessionId)

  return {
    ...currentView.store,
    connectionStatus: currentView.connectionStatus,
    error: currentView.error,
    isLoading: currentView.isLoading,
    sendMessage,
    steer,
    respond,
    cancel,
  }
}

function asError(value: unknown, fallback: string) {
  return value instanceof Error ? value : new Error(fallback)
}

function createCommandId() {
  return globalThis.crypto.randomUUID()
}

function initialView(sessionId: string): AgentSessionViewState {
  return {
    sessionId,
    store: initialAgentStoreState,
    connectionStatus: "connecting",
    error: null,
    isLoading: true,
  }
}
