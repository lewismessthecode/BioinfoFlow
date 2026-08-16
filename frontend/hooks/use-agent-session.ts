"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import {
  dispatchAgentCommand,
  getAgentSnapshot,
  updateAgentSession,
} from "@/lib/agent/client"
import { ApiError } from "@/lib/api"
import { subscribeAgentEvents } from "@/lib/agent/stream"
import {
  applyAgentEvent,
  initialAgentStoreState,
  type AgentStoreState,
} from "@/lib/agent/store"
import type {
  AgentCommand,
  AgentEvent,
  AgentPermissionMode,
  AgentExecutionScope,
  InputPart,
  InteractionResponse,
  SessionSnapshot,
} from "@/lib/agent/contracts"
import type { AgentConnectionStatus } from "@/lib/agent/stream"

export type AgentSessionState = AgentStoreState & {
  connectionStatus: AgentConnectionStatus
  error: Error | null
  isLoading: boolean
  sendMessage: (
    parts: InputPart[],
    runSettings?: {
      permission_mode?: AgentPermissionMode
      execution_scope?: AgentExecutionScope
    },
  ) => Promise<void>
  steer: (parts: InputPart[]) => Promise<void>
  respond: (
    interactionId: string,
    response: InteractionResponse,
  ) => Promise<void>
  cancel: () => Promise<void>
  updatePermissionMode: (mode: AgentPermissionMode) => Promise<void>
  retry: () => void
}

type AgentSessionViewState = {
  sessionId: string
  store: AgentStoreState
  connectionStatus: AgentConnectionStatus
  error: Error | null
  isLoading: boolean
}

export function useAgentSession(sessionId: string): AgentSessionState {
  const [retryRevision, setRetryRevision] = useState(0)
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
    let unsubscribe: (() => void) | null = null
    let snapshotRequest: Promise<boolean> | null = null
    let snapshotRefreshQueued = false
    let sessionMissing = false
    let viewFrame: number | null = null
    const generation = generationRef.current + 1

    generationRef.current = generation
    storeRef.current = initialAgentStoreState

    const cancelViewFrame = () => {
      if (viewFrame === null) return
      window.cancelAnimationFrame(viewFrame)
      viewFrame = null
    }

    const publishStore = (eventType?: AgentEvent["type"]) => {
      if (!active || generationRef.current !== generation) return
      const store = storeRef.current
      setView((current) => {
        const base =
          current.sessionId === sessionId ? current : initialView(sessionId)
        return {
          ...base,
          store,
          error: eventType === "snapshot" ? null : base.error,
          isLoading: eventType === "snapshot" ? false : base.isLoading,
        }
      })
    }

    const scheduleStorePublish = () => {
      if (viewFrame !== null) return
      viewFrame = window.requestAnimationFrame(() => {
        viewFrame = null
        publishStore()
      })
    }

    const refreshSnapshot = (): Promise<boolean> => {
      if (!active || sessionMissing) return Promise.resolve(false)
      if (snapshotRequest) {
        snapshotRefreshQueued = true
        return snapshotRequest
      }
      snapshotRequest = getAgentSnapshot(sessionId)
        .then((snapshot) => {
          if (!active) return false
          cancelViewFrame()
          const replaced = replaceSnapshot(generation, sessionId, snapshot)
          if (replaced && unsubscribe === null) {
            unsubscribe = subscribe()
          }
          return replaced
        })
        .catch((caught) => {
          if (!active) return false
          if (isMissingSessionError(caught)) {
            sessionMissing = true
            snapshotRefreshQueued = false
            unsubscribe?.()
            unsubscribe = null
            setView((current) => ({
              ...(current.sessionId === sessionId
                ? current
                : initialView(sessionId)),
              connectionStatus: "disconnected",
              error: asError(caught, "Agent session not found"),
              isLoading: false,
            }))
            return false
          }
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            connectionStatus: "disconnected",
            error: asError(caught, "Unable to load agent session"),
            isLoading: false,
          }))
          if (unsubscribe === null) {
            unsubscribe = subscribe()
          }
          return false
        })
        .finally(() => {
          snapshotRequest = null
          if (!active || sessionMissing || !snapshotRefreshQueued) return
          snapshotRefreshQueued = false
          void refreshSnapshot()
        })
      return snapshotRequest
    }

    const subscribe = () => {
      if (
        !active ||
        sessionMissing ||
        generationRef.current !== generation
      ) {
        return null
      }
      return subscribeAgentEvents({
        sessionId,
        onEvent,
        onConnectionChange: (status) => {
          if (!active || sessionMissing) return
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            connectionStatus: status,
          }))
        },
        onError: () => {
          if (!active || sessionMissing) return
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            error: new Error("Agent event stream disconnected"),
          }))
          void refreshSnapshot()
        },
        onProtocolError: () => {
          void refreshSnapshot()
        },
      })
    }

    const onEvent = (event: AgentEvent) => {
      if (!active || sessionMissing) return
      const application = applyAgentEvent(storeRef.current, event)
      if (application.outcome === "needs_snapshot") {
        void refreshSnapshot()
        return
      }
      if (application.outcome === "ignored") return
      storeRef.current = application.state
      if (event.type === "assistant.delta") {
        scheduleStorePublish()
        return
      }
      cancelViewFrame()
      publishStore(event.type)
    }

    void refreshSnapshot()

    return () => {
      active = false
      cancelViewFrame()
      if (generationRef.current === generation) generationRef.current += 1
      unsubscribe?.()
      unsubscribe = null
    }
  }, [replaceSnapshot, retryRevision, sessionId])

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
    (
      parts: InputPart[],
      runSettings?: {
        permission_mode?: AgentPermissionMode
        execution_scope?: AgentExecutionScope
      },
    ) =>
      runCommand({
        type: "message",
        command_id: createCommandId(),
        parts,
        run_settings: runSettings,
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

  const updatePermissionMode = useCallback(
    async (mode: AgentPermissionMode) => {
      const generation = generationRef.current
      setView((current) => ({
        ...(current.sessionId === sessionId
          ? current
          : initialView(sessionId)),
        error: null,
      }))
      try {
        await updateAgentSession(sessionId, { permissionMode: mode })
      } catch (caught) {
        if (generationRef.current === generation) {
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            error: asError(caught, "Agent session update failed"),
          }))
        }
        throw caught
      }
    },
    [sessionId],
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
    updatePermissionMode,
    retry: () => setRetryRevision((revision) => revision + 1),
  }
}

function asError(value: unknown, fallback: string) {
  return value instanceof Error ? value : new Error(fallback)
}

function isMissingSessionError(value: unknown): value is ApiError {
  return value instanceof ApiError && value.status === 404
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
