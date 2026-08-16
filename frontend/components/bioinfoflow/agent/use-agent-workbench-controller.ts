"use client"

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"

import type {
  AgentEnvironmentSelection,
  AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import {
  createAgentSession,
  updateAgentSession,
} from "@/lib/agent/client"
import {
  deleteAgentAttachment,
  type AgentContextInput,
} from "@/lib/agent/context"
import type {
  AgentPermissionMode,
  AgentWorkspaceAccess,
  SessionView,
} from "@/lib/agent/contracts"
import {
  fetchRemoteConnections,
  type RemoteConnection,
} from "@/lib/demo-connections"
import {
  publishAgentSessionSummary,
  sessionSummaryFromView,
} from "@/lib/agent/session-preferences"

export type DraftModelSelector = {
  modelId?: string
  provider?: string
  model?: string
}

type AgentWorkbenchControllerOptions = {
  sessionId: string | null
  projectId: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
  environmentTargets?: readonly AgentEnvironmentTarget[]
  requestedEnvironmentSelection?: AgentEnvironmentSelection
  effectiveEnvironmentSelection?: AgentEnvironmentSelection
  environmentSelectionPending: boolean
  onEnvironmentSelectionChange?: (
    selection: AgentEnvironmentSelection,
  ) => Promise<void>
}

export function useAgentWorkbenchController({
  sessionId,
  projectId,
  onActiveSessionIdChange,
  environmentTargets,
  requestedEnvironmentSelection,
  effectiveEnvironmentSelection,
  environmentSelectionPending,
  onEnvironmentSelectionChange,
}: AgentWorkbenchControllerOptions) {
  const router = useRouter()
  const tEnvironment = useTranslations("agentComposer.environment")
  const [localSessionId, setLocalSessionId] = useState<string | null>(null)
  const [draftSessionId, setDraftSessionId] = useState<string | null>(null)
  const [draftPermissionMode, setDraftPermissionMode] =
    useState<AgentPermissionMode>("ask_dangerous")
  const draftWorkspaceAccess: AgentWorkspaceAccess = "read_write"
  const [contextInputs, setContextInputs] = useState<AgentContextInput[]>([])
  const [localEnvironmentSelection, setLocalEnvironmentSelection] =
    useState<AgentEnvironmentSelection>({ mode: "auto" })
  const [draftEffectiveEnvironmentSelection, setDraftEffectiveEnvironmentSelection] =
    useState<AgentEnvironmentSelection>({ mode: "auto" })
  const [draftEnvironmentSelectionPending, setDraftEnvironmentSelectionPending] =
    useState(false)
  const [remoteConnections, setRemoteConnections] = useState<
    RemoteConnection[]
  >([])
  const [modelConnectionOpen, setModelConnectionOpen] = useState(false)
  const createPromiseRef = useRef<Promise<string> | null>(null)
  const cancelRef = useRef<(() => Promise<void>) | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const needsRouteSyncRef = useRef(sessionId === null)

  const visibleEnvironmentSelection =
    requestedEnvironmentSelection ?? localEnvironmentSelection
  const visibleEnvironmentTargets = useMemo<readonly AgentEnvironmentTarget[]>(
    () =>
      environmentTargets ?? [
        {
          id: "local",
          label: tEnvironment("local"),
          kind: "local",
          status: "online",
        },
        ...remoteConnections.map(environmentTargetFromConnection),
      ],
    [environmentTargets, remoteConnections, tEnvironment],
  )

  useEffect(() => {
    if (environmentTargets) return
    let active = true
    void fetchRemoteConnections()
      .then((connections) => {
        if (active) setRemoteConnections(connections)
      })
      .catch(() => {
        if (active) setRemoteConnections([])
      })
    return () => {
      active = false
    }
  }, [environmentTargets])

  const updateEnvironmentSelection = useCallback(
    async (selection: AgentEnvironmentSelection) => {
      if (onEnvironmentSelectionChange) {
        await onEnvironmentSelectionChange(selection)
        return
      }

      const previousSelection = localEnvironmentSelection
      setLocalEnvironmentSelection(selection)
      if (!draftSessionId) {
        setDraftEffectiveEnvironmentSelection(selection)
        return
      }

      setDraftEnvironmentSelectionPending(true)
      try {
        const snapshot = await updateAgentSession(draftSessionId, {
          environmentScope: environmentScopeFromSelection(selection),
        })
        publishAgentSessionSummary(sessionSummaryFromView(snapshot.session))
        const confirmedSelection = environmentSelectionFromSession(
          snapshot.session,
        )
        setLocalEnvironmentSelection(confirmedSelection)
        setDraftEffectiveEnvironmentSelection(confirmedSelection)
      } catch (error) {
        setLocalEnvironmentSelection(previousSelection)
        throw error
      } finally {
        setDraftEnvironmentSelectionPending(false)
      }
    },
    [
      draftSessionId,
      localEnvironmentSelection,
      onEnvironmentSelectionChange,
    ],
  )

  const effectiveSessionId = sessionId ?? localSessionId
  const setCancelHandler = useCallback(
    (handler: (() => Promise<void>) | null) => {
      cancelRef.current = handler
    },
    [],
  )

  const ensureSession = useCallback(
    (modelSelector?: DraftModelSelector) => {
      if (effectiveSessionId) return Promise.resolve(effectiveSessionId)
      if (draftSessionId) return Promise.resolve(draftSessionId)
      if (createPromiseRef.current) return createPromiseRef.current

      const request = createAgentSession({
        projectId,
        permissionMode: draftPermissionMode,
        workspaceAccess: draftWorkspaceAccess,
        environmentScope: environmentScopeFromSelection(
          visibleEnvironmentSelection,
        ),
        ...modelSelector,
      })
        .then((snapshot) => {
          const id = snapshot.session.id
          publishAgentSessionSummary(sessionSummaryFromView(snapshot.session))
          const confirmedSelection = environmentSelectionFromSession(
            snapshot.session,
          )
          setLocalEnvironmentSelection(confirmedSelection)
          setDraftEffectiveEnvironmentSelection(confirmedSelection)
          setDraftSessionId(id)
          return id
        })
        .finally(() => {
          createPromiseRef.current = null
        })
      createPromiseRef.current = request
      return request
    },
    [
      draftPermissionMode,
      draftSessionId,
      effectiveSessionId,
      projectId,
      visibleEnvironmentSelection,
    ],
  )

  const routeToSession = useCallback(
    (id: string) => {
      if (!needsRouteSyncRef.current) return
      needsRouteSyncRef.current = false
      setLocalSessionId(id)
      onActiveSessionIdChange?.(id)
      router.replace(`/agent/${id}`)
    },
    [onActiveSessionIdChange, router],
  )

  const addContextInput = useCallback((input: AgentContextInput) => {
    setContextInputs((current) =>
      current.some((item) => item.id === input.id)
        ? current
        : [...current, input],
    )
  }, [])

  const removeContextInput = useCallback((inputId: string) => {
    setContextInputs((current) => {
      const removed = current.find((item) => item.id === inputId)
      if (removed?.input_part.type === "attachment_ref") {
        void deleteAgentAttachment(removed.input_part.attachment_id)
      }
      return current.filter((item) => item.id !== inputId)
    })
  }, [])

  const updateDraftPermissionMode = useCallback(
    async (mode: AgentPermissionMode) => {
      if (!draftSessionId) {
        setDraftPermissionMode(mode)
        return
      }

      const snapshot = await updateAgentSession(draftSessionId, {
        permissionMode: mode,
      })
      publishAgentSessionSummary(sessionSummaryFromView(snapshot.session))
      setDraftPermissionMode(snapshot.session.permission_mode)
    },
    [draftSessionId],
  )

  const stop = useCallback(() => void cancelRef.current?.(), [])
  const newConversation = useCallback(() => {
    setLocalSessionId(null)
    setDraftSessionId(null)
    onActiveSessionIdChange?.("")
    router.push("/agent")
  }, [onActiveSessionIdChange, router])

  return {
    effectiveSessionId,
    draftSessionId,
    draftPermissionMode,
    draftWorkspaceAccess,
    contextInputs,
    setContextInputs,
    addContextInput,
    removeContextInput,
    ensureSession,
    routeToSession,
    textareaRef,
    setCancelHandler,
    stop,
    newConversation,
    modelConnectionOpen,
    setModelConnectionOpen,
    visibleEnvironmentTargets,
    visibleEnvironmentSelection,
    effectiveEnvironmentSelection:
      effectiveEnvironmentSelection ??
      (requestedEnvironmentSelection
        ? visibleEnvironmentSelection
        : draftEffectiveEnvironmentSelection),
    environmentSelectionPending:
      environmentSelectionPending || draftEnvironmentSelectionPending,
    updateEnvironmentSelection,
    updateDraftPermissionMode,
    hasControlledEnvironmentSelection:
      requestedEnvironmentSelection !== undefined ||
      effectiveEnvironmentSelection !== undefined ||
      onEnvironmentSelectionChange !== undefined,
  }
}

function environmentSelectionFromSession(
  session: SessionView,
): AgentEnvironmentSelection {
  const scope = session.environment_scope
  return scope?.mode === "manual"
    ? { mode: "manual", targetIds: scope.selected_environment_ids }
    : { mode: "auto" }
}

export function environmentScopeFromSelection(
  selection: AgentEnvironmentSelection,
) {
  return selection.mode === "manual"
    ? { mode: "manual" as const, selected_environment_ids: selection.targetIds }
    : { mode: "auto" as const }
}

export function environmentSelectionEquals(
  left: AgentEnvironmentSelection,
  right: AgentEnvironmentSelection,
) {
  if (left.mode !== right.mode) return false
  if (left.mode === "auto" || right.mode === "auto") return true
  return (
    left.targetIds.length === right.targetIds.length &&
    left.targetIds.every((targetId, index) => targetId === right.targetIds[index])
  )
}

function environmentTargetFromConnection(
  connection: RemoteConnection,
): AgentEnvironmentTarget {
  return {
    id: connection.id,
    label: connection.name.trim() || connection.host,
    description: `${connection.username}@${connection.host}:${connection.port}`,
    kind: "ssh",
    status: connection.status,
  }
}
