"use client"

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import type { RefObject } from "react"
import type { ReactNode } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"

import { AgentComposer } from "@/components/bioinfoflow/agent/agent-composer"
import { AgentContextPicker } from "@/components/bioinfoflow/agent/agent-context-picker"
import { AgentModelConnectionDialog } from "@/components/bioinfoflow/agent/agent-model-connection-dialog"
import { AgentTranscript } from "@/components/bioinfoflow/agent/agent-transcript"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useAgentSession,
  type AgentSessionState,
} from "@/hooks/use-agent-session"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import {
  createAgentSession,
  dispatchAgentCommand,
  updateAgentSession,
} from "@/lib/agent/client"
import {
  deleteAgentAttachment,
  type AgentContextInput,
} from "@/lib/agent/context"
import type {
  AgentPermissionMode,
  AgentWorkspaceAccess,
  InputPart,
  SessionView,
} from "@/lib/agent/contracts"
import {
  publishAgentSessionSummary,
  sessionSummaryFromView,
} from "@/lib/agent/session-preferences"
import { ApiError } from "@/lib/api"
import {
  Bot,
  CircleAlert,
  Loader2,
  RefreshCw,
  Wifi,
  WifiOff,
} from "@/lib/icons"
import { cn } from "@/lib/utils"

export type AgentWorkbenchHandle = {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

type AgentWorkbenchProps = {
  sessionId: string | null
  projectId: string | null
  sessionState?: AgentSessionState
  interactive?: boolean
  onActiveSessionIdChange?: (sessionId: string) => void
  onSessionResolved?: (session: SessionView) => void
  headerActions?: ReactNode
  className?: string
}

type DraftModelSelector = {
  modelId?: string
  provider?: string
  model?: string
}

export const AgentWorkbench = forwardRef<
  AgentWorkbenchHandle,
  AgentWorkbenchProps
>(function AgentWorkbench(
  {
    sessionId,
    projectId,
    sessionState,
    interactive = true,
    onActiveSessionIdChange,
    onSessionResolved,
    headerActions,
    className,
  },
  ref,
) {
  const router = useRouter()
  const [localSessionId, setLocalSessionId] = useState<string | null>(null)
  const [draftSessionId, setDraftSessionId] = useState<string | null>(null)
  const [draftPermissionMode, setDraftPermissionMode] =
    useState<AgentPermissionMode>("ask_dangerous")
  const [draftWorkspaceAccess] =
    useState<AgentWorkspaceAccess>("read_write")
  const [contextInputs, setContextInputs] = useState<AgentContextInput[]>([])
  const [modelConnectionOpen, setModelConnectionOpen] = useState(false)
  const createPromiseRef = useRef<Promise<string> | null>(null)
  const cancelRef = useRef<(() => Promise<void>) | null>(null)
  const textareaRef = useRef<HTMLTextAreaElement>(null)
  const needsRouteSyncRef = useRef(sessionId === null)

  const effectiveSessionId = sessionId ?? localSessionId
  const setCancelHandler = useCallback(
    (handler: (() => Promise<void>) | null) => {
      cancelRef.current = handler
    },
    [],
  )

  const ensureSession = useCallback((modelSelector?: DraftModelSelector) => {
    if (effectiveSessionId) return Promise.resolve(effectiveSessionId)
    if (draftSessionId) return Promise.resolve(draftSessionId)
    if (createPromiseRef.current) return createPromiseRef.current

    const request = createAgentSession({
      projectId,
      permissionMode: draftPermissionMode,
      workspaceAccess: draftWorkspaceAccess,
      ...modelSelector,
    })
      .then((snapshot) => {
        const id = snapshot.session.id
        publishAgentSessionSummary(sessionSummaryFromView(snapshot.session))
        setDraftSessionId(id)
        return id
      })
      .finally(() => {
        createPromiseRef.current = null
      })
    createPromiseRef.current = request
    return request
  }, [
    draftPermissionMode,
    draftWorkspaceAccess,
    draftSessionId,
    effectiveSessionId,
    projectId,
  ])

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
      current.some((item) => item.id === input.id) ? current : [...current, input],
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

  useImperativeHandle(
    ref,
    () => ({
      focusInput: () => textareaRef.current?.focus(),
      stop: () => void cancelRef.current?.(),
      newConversation: () => {
        setLocalSessionId(null)
        setDraftSessionId(null)
        onActiveSessionIdChange?.("")
        router.push("/agent")
      },
    }),
    [onActiveSessionIdChange, router],
  )

  const common = {
    projectId,
    contextInputs,
    setContextInputs,
    addContextInput,
    removeContextInput,
    ensureSession,
    routeToSession,
    textareaRef,
    setCancelHandler,
    setModelConnectionOpen,
  }

  return (
    <main
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col bg-background",
        className,
      )}
      data-testid="agent-workbench"
    >
      {effectiveSessionId ? (
        sessionState ? (
          <SessionWorkbench
            key={effectiveSessionId}
            sessionId={effectiveSessionId}
            state={sessionState}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            headerActions={headerActions}
            {...common}
          />
        ) : (
          <LiveSessionWorkbench
            key={effectiveSessionId}
            sessionId={effectiveSessionId}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            headerActions={headerActions}
            {...common}
          />
        )
      ) : (
        <DraftWorkbench
          permissionMode={draftPermissionMode}
          workspaceAccess={draftWorkspaceAccess}
          draftSessionId={draftSessionId}
          onPermissionModeChange={updateDraftPermissionMode}
          headerActions={headerActions}
          {...common}
        />
      )}
      <AgentModelConnectionDialog
        open={modelConnectionOpen}
        onOpenChange={setModelConnectionOpen}
      />
    </main>
  )
})

type SharedWorkbenchProps = {
  projectId: string | null
  contextInputs: AgentContextInput[]
  setContextInputs: (inputs: AgentContextInput[]) => void
  addContextInput: (input: AgentContextInput) => void
  removeContextInput: (inputId: string) => void
  ensureSession: (modelSelector?: DraftModelSelector) => Promise<string>
  routeToSession: (sessionId: string) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  setCancelHandler: (handler: (() => Promise<void>) | null) => void
  setModelConnectionOpen: (open: boolean) => void
}

function DraftWorkbench({
  permissionMode,
  workspaceAccess,
  draftSessionId,
  onPermissionModeChange,
  headerActions,
  ...shared
}: SharedWorkbenchProps & {
  permissionMode: AgentPermissionMode
  workspaceAccess: AgentWorkspaceAccess
  draftSessionId: string | null
  onPermissionModeChange: (mode: AgentPermissionMode) => Promise<void>
  headerActions?: ReactNode
}) {
  const t = useTranslations("agentWorkbench")
  const [error, setError] = useState<string | null>(null)
  const { models, selectedModel, setSelectedModel, isLoading } = useLlmSettings()
  const ensureSession = shared.ensureSession
  const ensureDraftSession = useCallback(
    () => {
      const modelSelector: DraftModelSelector | undefined = selectedModel
        ? selectedModel.model_id
          ? { modelId: selectedModel.model_id }
          : selectedModel.provider && selectedModel.model
            ? { provider: selectedModel.provider, model: selectedModel.model }
            : undefined
        : undefined
      return ensureSession(modelSelector)
    },
    [ensureSession, selectedModel],
  )

  const send = async (parts: InputPart[]) => {
    setError(null)
    shared.setModelConnectionOpen(false)
    try {
      const sessionId = await ensureDraftSession()
      await dispatchAgentCommand(sessionId, {
        type: "message",
        command_id: globalThis.crypto.randomUUID(),
        parts,
      })
      shared.setContextInputs([])
      shared.routeToSession(sessionId)
    } catch (caught) {
      if (isModelConfigurationError(caught)) {
        shared.setModelConnectionOpen(true)
      } else {
        setError(t("createError"))
      }
      throw new Error("Unable to create agent session")
    }
  }

  return (
    <div className="relative flex min-h-0 flex-1 flex-col">
      {headerActions ? (
        <div className="absolute right-3 top-3 z-10">{headerActions}</div>
      ) : null}
      <div
        data-testid="agent-draft-entry"
        className="flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-2 py-10 sm:px-6"
      >
        <AgentEmptyState compact />
        {error ? <WorkbenchError message={error} embedded /> : null}
        <AgentComposer
          placement="draft"
          permissionMode={permissionMode}
          workspaceAccess={workspaceAccess}
          activeRun={null}
          onSendMessage={send}
          onSteer={send}
          onCancel={async () => {}}
          onPermissionModeChange={onPermissionModeChange}
          contextInputs={shared.contextInputs}
          onRemoveContextInput={shared.removeContextInput}
          onContextSubmitted={() => shared.setContextInputs([])}
          textareaRef={shared.textareaRef}
          contextControls={
            <AgentContextPicker
              projectId={shared.projectId}
              sessionId={draftSessionId}
              ensureSession={ensureDraftSession}
              onAdd={shared.addContextInput}
            />
          }
          modelControls={
            <ModelSelector
              models={models}
              selectedModel={selectedModel}
              onSelectModel={(selection) => void setSelectedModel(selection)}
              disabled={isLoading || draftSessionId !== null}
              variant="composer"
            />
          }
        />
      </div>
    </div>
  )
}

function LiveSessionWorkbench({
  sessionId,
  ...props
}: SharedWorkbenchProps & {
  sessionId: string
  interactive: boolean
  onSessionResolved?: (session: SessionView) => void
  headerActions?: ReactNode
}) {
  const state = useAgentSession(sessionId)
  return <SessionWorkbench sessionId={sessionId} state={state} {...props} />
}

function SessionWorkbench({
  sessionId,
  state,
  interactive,
  onSessionResolved,
  headerActions,
  ...shared
}: SharedWorkbenchProps & {
  sessionId: string
  state: AgentSessionState
  interactive: boolean
  onSessionResolved?: (session: SessionView) => void
  headerActions?: ReactNode
}) {
  const t = useTranslations("agentWorkbench")
  const setCancelHandler = shared.setCancelHandler

  useEffect(() => {
    setCancelHandler(interactive ? state.cancel : null)
    return () => {
      setCancelHandler(null)
    }
  }, [interactive, setCancelHandler, state.cancel])

  useEffect(() => {
    if (!state.session) return
    publishAgentSessionSummary(sessionSummaryFromView(state.session))
    onSessionResolved?.(state.session)
  }, [onSessionResolved, state.session])

  const runSessionCommand = async (command: () => Promise<void>) => {
    shared.setModelConnectionOpen(false)
    try {
      await command()
    } catch (caught) {
      if (isModelConfigurationError(caught)) {
        shared.setModelConnectionOpen(true)
      }
      throw caught
    }
  }

  const sendMessage = async (parts: InputPart[]) => {
    await runSessionCommand(() => state.sendMessage(parts))
    shared.setContextInputs([])
    shared.routeToSession(sessionId)
  }
  const steer = async (parts: InputPart[]) => {
    await runSessionCommand(() => state.steer(parts))
    shared.setContextInputs([])
  }

  if (state.isLoading && !state.session) return <WorkbenchSkeleton />
  if (!state.session) {
    return (
      <div className="grid min-h-0 flex-1 place-items-center px-6 text-center">
        <div className="flex max-w-sm flex-col items-center gap-3">
          <CircleAlert aria-hidden="true" className="mx-auto text-destructive" />
          <h1 className="text-base font-medium">{t("loadErrorTitle")}</h1>
          <p className="text-sm text-muted-foreground">
            {state.error?.message ?? t("loadErrorDescription")}
          </p>
          <Button type="button" variant="outline" onClick={state.retry}>
            <RefreshCw data-icon="inline-start" aria-hidden="true" />
            {t("retry")}
          </Button>
        </div>
      </div>
    )
  }

  const isEmpty = state.entries.length === 0 && !state.activeRun
  return (
    <>
      <ConversationHeader
        title={state.session.title || t("untitled")}
        connectionStatus={state.connectionStatus}
        actions={headerActions}
      />
      {state.error &&
      ["reconnecting", "disconnected"].includes(state.connectionStatus) ? (
        <div
          role="status"
          className="flex items-center justify-center gap-2 border-b bg-muted/25 px-3 py-1.5 text-xs text-muted-foreground"
        >
          <WifiOff aria-hidden="true" />
          {t(`connection.${state.connectionStatus}`)}
        </div>
      ) : null}
      {isEmpty ? (
        <AgentEmptyState />
      ) : (
        <AgentTranscript
          className="flex-1"
          entries={state.entries}
          runs={state.runs}
          activeRun={state.activeRun}
          onRespond={interactive ? state.respond : undefined}
        />
      )}
      {state.session.status !== "active" ? (
        <p
          role="status"
          className="border-t border-border/70 bg-muted/25 px-4 py-2 text-center text-xs leading-5 text-muted-foreground"
        >
          {t(`readOnly.${state.session.status}`)}
        </p>
      ) : null}
      <AgentComposer
        placement="dock"
        permissionMode={state.session.permission_mode}
        workspaceAccess={state.session.workspace_access}
        activeRun={state.activeRun}
        onSendMessage={sendMessage}
        onSteer={steer}
        onCancel={state.cancel}
        onPermissionModeChange={state.updatePermissionMode}
        contextInputs={shared.contextInputs}
        onRemoveContextInput={shared.removeContextInput}
        onContextSubmitted={() => shared.setContextInputs([])}
        textareaRef={shared.textareaRef}
        disabled={!interactive || state.session.status !== "active"}
        contextControls={
          <AgentContextPicker
            projectId={state.session.project_id}
            sessionId={sessionId}
            ensureSession={shared.ensureSession}
            onAdd={shared.addContextInput}
            disabled={!interactive || state.session.status !== "active"}
          />
        }
        modelControls={<ComposerModelLabel label={state.session.model.display_name} />}
      />
    </>
  )
}

function ConversationHeader({
  title,
  connectionStatus,
  actions,
}: {
  title: string
  connectionStatus?:
    | "connecting"
    | "connected"
    | "reconnecting"
    | "disconnected"
  actions?: ReactNode
}) {
  const t = useTranslations("agentWorkbench")
  const ConnectionIcon =
    connectionStatus === "connected"
      ? Wifi
      : connectionStatus === "reconnecting" || connectionStatus === "disconnected"
        ? WifiOff
        : Loader2
  return (
    <header className="flex min-w-0 items-center gap-3 border-b px-4 py-2.5">
      <Bot aria-hidden="true" className="shrink-0 text-muted-foreground" />
      <h1 className="min-w-0 flex-1 truncate text-sm font-medium">{title}</h1>
      {connectionStatus ? (
        <span
          className="flex items-center gap-1.5 text-xs text-muted-foreground"
          title={t(`connection.${connectionStatus}`)}
          aria-label={t(`connection.${connectionStatus}`)}
        >
          <ConnectionIcon
            aria-hidden="true"
            className={cn(
              connectionStatus === "connecting" &&
                "animate-spin motion-reduce:animate-none",
            )}
          />
          <span className="hidden sm:inline">{t(`connection.${connectionStatus}`)}</span>
        </span>
      ) : null}
      {actions}
    </header>
  )
}

function AgentEmptyState({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("agentWorkbench")
  return (
    <div className={cn("grid place-items-center px-6 text-center", compact ? "pb-5" : "min-h-0 flex-1 py-10")}>
      <div className="max-w-lg">
        <Bot aria-hidden="true" className="mx-auto mb-4 size-7 text-muted-foreground" />
        <h2 className={cn("font-medium tracking-tight", compact ? "text-xl sm:text-2xl" : "text-base")}>{t("emptyTitle")}</h2>
        <p className="mt-2 text-sm leading-6 text-muted-foreground">
          {t("emptyDescription")}
        </p>
      </div>
    </div>
  )
}

function WorkbenchError({
  message,
  embedded = false,
}: {
  message: string
  embedded?: boolean
}) {
  return (
    <div className={cn("w-full px-4 py-3", !embedded && "border-t")}>
      <Alert variant="destructive" className="mx-auto max-w-[46rem]">
        <CircleAlert aria-hidden="true" />
        <AlertTitle>{message}</AlertTitle>
      </Alert>
    </div>
  )
}

function ComposerModelLabel({ label }: { label: string }) {
  return (
    <span
      className="inline-flex min-h-7 min-w-0 max-w-[168px] items-center truncate rounded-[8px] px-2 text-[11px] font-medium text-foreground/68"
      title={label}
    >
      {label}
    </span>
  )
}

function isModelConfigurationError(error: unknown) {
  return (
    error instanceof ApiError &&
    error.code === "AGENT_MODEL_REQUIRED" &&
    error.status === 422
  )
}

function WorkbenchSkeleton() {
  return (
    <div className="flex min-h-0 flex-1 flex-col" aria-busy="true">
      <div className="flex items-center gap-3 border-b px-4 py-3">
        <Skeleton className="size-5 rounded-full" />
        <div className="flex flex-col gap-1.5">
          <Skeleton className="h-3.5 w-36" />
          <Skeleton className="h-3 w-20" />
        </div>
      </div>
      <div className="mx-auto flex w-full max-w-[46rem] flex-1 flex-col gap-5 px-4 py-8">
        <Skeleton className="h-14 w-2/3" />
        <Skeleton className="ml-auto h-20 w-3/4" />
      </div>
    </div>
  )
}
