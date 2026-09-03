"use client"

import { useCallback, useEffect, useRef, useState } from "react"

import {
  dispatchAgentCommand,
  getAgentSnapshot,
  updateAgentSession,
  type AgentModelSelection,
  type AgentSessionUpdates,
} from "@/lib/agent/client"
import { ApiError } from "@/lib/api"
import { subscribeAgentEvents } from "@/lib/agent/stream"
import {
  initialAgentStoreState,
  type AgentStoreState,
} from "@/lib/agent/store"
import type {
  ConversationEnvironmentScope,
  ConversationSessionBinding,
  ConversationViewModel,
} from "@/lib/agent/conversation-model/types"
import {
  applyConversationProjectionDiagnostic,
  applyConversationProjectionEvent,
  applyConversationSessionTitle,
  createConversationProjection,
  type ConversationProjectionState,
} from "@/lib/agent/projection/conversation-projection"
import type {
  AgentCommand,
  AgentEvent,
  AgentEnvironmentScope,
  AgentPermissionMode,
  InputPart,
  InteractionResponse,
  SessionSnapshot,
} from "@/lib/agent/contracts"
import type { AgentConnectionStatus } from "@/lib/agent/stream"
import type { PresentationDiagnostic } from "@/lib/agent/transport/presentation-contract"

export type AgentSessionState = ConversationSessionBinding & AgentStoreState & {
  /** @deprecated Use `view`. */
  conversationView: ConversationViewModel | null
  connectionStatus: AgentConnectionStatus
  error: Error | null
  isLoading: boolean
  /** @deprecated Use `commands.sendMessage`. */
  sendMessage: (parts: InputPart[]) => Promise<void>
  /** @deprecated Use `commands.steer`. */
  steer: (parts: InputPart[]) => Promise<void>
  /** @deprecated Use `commands.respond`. */
  respond: (
    interactionId: string,
    response: InteractionResponse,
  ) => Promise<void>
  /** @deprecated Use `commands.cancel`. */
  cancel: () => Promise<void>
  /** @deprecated Use `commands.updatePermissionMode`. */
  updatePermissionMode: (mode: AgentPermissionMode) => Promise<void>
  /** @deprecated Use `commands.updateModel`. */
  updateModel: (selection: AgentModelSelection) => Promise<void>
  /** @deprecated Use `commands.updateEnvironmentScope`. */
  updateEnvironmentScope: (scope: AgentEnvironmentScope) => Promise<void>
  /** @deprecated Use `commands.retry`. */
  retry: () => void
}

type AgentSessionViewState = {
  sessionId: string
  store: AgentStoreState
  conversationView: ConversationViewModel | null
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
  const projectionRef = useRef<ConversationProjectionState | null>(null)
  const conversationViewRef = useRef<ConversationViewModel | null>(null)
  const generationRef = useRef(0)

  const replaceSnapshot = useCallback(
    (
      expectedGeneration: number,
      expectedSessionId: string,
      snapshot: SessionSnapshot,
    ) => {
      if (generationRef.current !== expectedGeneration) return false
      const projection = createConversationProjection(snapshot)
      if (!projection.ok) {
        setView((current) => ({
          ...(current.sessionId === expectedSessionId
            ? current
            : initialView(expectedSessionId)),
          error: new Error(projection.diagnostic.message),
          isLoading: false,
        }))
        return false
      }
      projectionRef.current = projection.state
      conversationViewRef.current = projection.view
      storeRef.current = projection.state.transportState
      setView((current) => ({
        ...(current.sessionId === expectedSessionId
          ? current
          : initialView(expectedSessionId)),
        store: projection.state.transportState,
        conversationView: projection.view,
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
    let streamRecoveryPending = false
    let streamRevision = 0
    let viewFrame: number | null = null
    const generation = generationRef.current + 1

    generationRef.current = generation
    storeRef.current = initialAgentStoreState
    projectionRef.current = null
    conversationViewRef.current = null

    const cancelViewFrame = () => {
      if (viewFrame === null) return
      window.cancelAnimationFrame(viewFrame)
      viewFrame = null
    }

    const publishStore = (eventType?: AgentEvent["type"]) => {
      if (!active || generationRef.current !== generation) return
      const store = storeRef.current
      const conversationView = conversationViewRef.current
      setView((current) => {
        const base =
          current.sessionId === sessionId ? current : initialView(sessionId)
        return {
          ...base,
          store,
          conversationView,
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

    const disposeStream = () => {
      streamRevision += 1
      const dispose = unsubscribe
      unsubscribe = null
      dispose?.()
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
          if (replaced) streamRecoveryPending = false
          return replaced
        })
        .catch((caught) => {
          if (!active) return false
          if (isMissingSessionError(caught)) {
            sessionMissing = true
            snapshotRefreshQueued = false
            disposeStream()
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
          if (unsubscribe === null && !streamRecoveryPending) {
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
      const revision = streamRevision + 1
      streamRevision = revision
      const isCurrentStream = () =>
        active &&
        !sessionMissing &&
        generationRef.current === generation &&
        streamRevision === revision
      return subscribeAgentEvents({
        sessionId,
        onEvent: (event) => {
          if (!isCurrentStream()) return
          onEvent(event)
        },
        onDiagnostic: (diagnostic) => {
          if (!isCurrentStream()) return
          onDiagnostic(diagnostic)
        },
        onConnectionChange: (status) => {
          if (!isCurrentStream()) return
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            connectionStatus: status,
          }))
        },
        onError: () => {
          if (!isCurrentStream()) return
          streamRecoveryPending = true
          disposeStream()
          setView((current) => ({
            ...(current.sessionId === sessionId
              ? current
              : initialView(sessionId)),
            error: new Error("Agent event stream disconnected"),
          }))
          void refreshSnapshot()
        },
      })
    }

    const onEvent = (event: AgentEvent) => {
      if (!active || sessionMissing) return
      if (event.type === "snapshot") {
        cancelViewFrame()
        replaceSnapshot(generation, sessionId, event.snapshot)
        return
      }
      const currentProjection = projectionRef.current
      if (!currentProjection) {
        void refreshSnapshot()
        return
      }
      const application = applyConversationProjectionEvent(
        currentProjection,
        event,
      )
      if (application.outcome === "needs_snapshot") {
        void refreshSnapshot()
        return
      }
      if (application.outcome === "ignored") return
      projectionRef.current = application.state
      conversationViewRef.current = application.view
      storeRef.current = application.state.transportState
      if (event.type === "assistant.delta") {
        scheduleStorePublish()
        return
      }
      cancelViewFrame()
      publishStore(event.type)
    }

    const onDiagnostic = (diagnostic: PresentationDiagnostic) => {
      if (!active || sessionMissing || !projectionRef.current) return
      const application = applyConversationProjectionDiagnostic(
        projectionRef.current,
        diagnostic,
      )
      projectionRef.current = application.state
      conversationViewRef.current = application.view
      cancelViewFrame()
      publishStore()
    }

    void refreshSnapshot()

    return () => {
      active = false
      cancelViewFrame()
      if (generationRef.current === generation) generationRef.current += 1
      disposeStream()
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
        const snapshot = await dispatchAgentCommand(sessionId, command)
        if (generationRef.current !== generation) return
        const currentProjection = projectionRef.current
        if (!currentProjection) return
        const application = applyConversationSessionTitle(
          currentProjection,
          snapshot.session,
        )
        if (application.outcome === "ignored") return
        projectionRef.current = application.state
        conversationViewRef.current = application.view
        storeRef.current = application.state.transportState
        setView((current) =>
          current.sessionId === sessionId
            ? {
                ...current,
                store: application.state.transportState,
                conversationView: application.view,
              }
            : current,
        )
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

  const updateSessionSettings = useCallback(
    async (updates: AgentSessionUpdates) => {
      const generation = generationRef.current
      setView((current) => ({
        ...(current.sessionId === sessionId
          ? current
          : initialView(sessionId)),
        error: null,
      }))
      try {
        await updateAgentSession(sessionId, updates)
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

  const updatePermissionMode = useCallback(
    (mode: AgentPermissionMode) =>
      updateSessionSettings({ permissionMode: mode }),
    [updateSessionSettings],
  )

  const updateModel = useCallback(
    (selection: AgentModelSelection) =>
      updateSessionSettings({ model: selection }),
    [updateSessionSettings],
  )

  const updateEnvironmentScope = useCallback(
    (scope: AgentEnvironmentScope) =>
      updateSessionSettings({ environmentScope: scope }),
    [updateSessionSettings],
  )

  const currentView =
    view.sessionId === sessionId ? view : initialView(sessionId)

  return {
    ...currentView.store,
    conversationView: currentView.conversationView,
    view: currentView.conversationView,
    connectionStatus: currentView.connectionStatus,
    error: currentView.error,
    isLoading: currentView.isLoading,
    sendMessage,
    steer,
    respond,
    cancel,
    updatePermissionMode,
    updateModel,
    updateEnvironmentScope,
    retry: () => setRetryRevision((revision) => revision + 1),
    commands: {
      sendMessage: (parts) => sendMessage(parts),
      steer: (parts) => steer(parts),
      respond: (interactionId, response) => respond(interactionId, response),
      cancel: () => cancel(),
      updatePermissionMode: (mode) => updatePermissionMode(mode),
      updateModel: (selection) => updateModel(selection),
      updateEnvironmentScope: (scope) =>
        updateEnvironmentScope(environmentScopeFromConversation(scope)),
      retry: () => setRetryRevision((revision) => revision + 1),
    },
  }
}

function environmentScopeFromConversation(
  scope: ConversationEnvironmentScope,
): AgentEnvironmentScope {
  return scope.mode === "manual"
    ? { mode: "manual", selected_environment_ids: scope.environmentIds }
    : { mode: "auto" }
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
    conversationView: null,
    connectionStatus: "connecting",
    error: null,
    isLoading: true,
  }
}
