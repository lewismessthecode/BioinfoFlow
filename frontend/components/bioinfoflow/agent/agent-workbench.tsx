"use client"

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useState,
} from "react"
import type { RefObject } from "react"
import type { ReactNode } from "react"
import { useLocale, useTranslations } from "next-intl"

import { AgentComposer } from "@/components/bioinfoflow/agent/agent-composer"
import type {
  AgentEnvironmentSelection,
  AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import { AgentContextPicker } from "@/components/bioinfoflow/agent/agent-context-picker"
import { AgentModelConnectionDialog } from "@/components/bioinfoflow/agent/agent-model-connection-dialog"
import { ConversationTranscript } from "@/components/bioinfoflow/agent/conversation-transcript"
import {
  environmentScopeFromSelection,
  environmentSelectionEquals,
  environmentSelectionFromSession,
  useAgentWorkbenchController,
  type DraftModelSelector,
} from "@/components/bioinfoflow/agent/use-agent-workbench-controller"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import {
  useAgentSession,
  type AgentSessionState,
} from "@/hooks/use-agent-session"
import { useAgentStarterPrompts } from "@/hooks/use-agent-starter-prompts"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import type { ModelSelection } from "@/hooks/use-llm-settings"
import {
  dispatchAgentCommand,
  updateAgentSession,
} from "@/lib/agent/client"
import type { AgentContextInput } from "@/lib/agent/context"
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
import { Bot, CircleAlert, Loader2, RefreshCw, WifiOff } from "@/lib/icons"
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
  onOpenRun?: (runId: string) => void
  headerActions?: ReactNode
  conversationModelControls?: ReactNode
  environmentTargets?: readonly AgentEnvironmentTarget[]
  requestedEnvironmentSelection?: AgentEnvironmentSelection
  effectiveEnvironmentSelection?: AgentEnvironmentSelection
  environmentSelectionPending?: boolean
  onEnvironmentSelectionChange?: (
    selection: AgentEnvironmentSelection,
  ) => Promise<void>
  starterPrompts?: readonly string[]
  className?: string
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
    onOpenRun,
    headerActions,
    conversationModelControls,
    environmentTargets,
    requestedEnvironmentSelection,
    effectiveEnvironmentSelection,
    environmentSelectionPending = false,
    onEnvironmentSelectionChange,
    starterPrompts,
    className,
  },
  ref,
) {
  const controller = useAgentWorkbenchController({
    sessionId,
    projectId,
    onActiveSessionIdChange,
    environmentTargets,
    requestedEnvironmentSelection,
    effectiveEnvironmentSelection,
    environmentSelectionPending,
    onEnvironmentSelectionChange,
  })

  useImperativeHandle(
    ref,
    () => ({
      focusInput: () => controller.textareaRef.current?.focus(),
      stop: controller.stop,
      newConversation: controller.newConversation,
    }),
    [controller.newConversation, controller.stop, controller.textareaRef],
  )

  const common = {
    projectId,
    contextInputs: controller.contextInputs,
    setContextInputs: controller.setContextInputs,
    addContextInput: controller.addContextInput,
    removeContextInput: controller.removeContextInput,
    ensureSession: controller.ensureSession,
    routeToSession: controller.routeToSession,
    textareaRef: controller.textareaRef,
    setCancelHandler: controller.setCancelHandler,
    setModelConnectionOpen: controller.setModelConnectionOpen,
    onOpenRun,
    conversationModelControls,
    environmentTargets: controller.visibleEnvironmentTargets,
    environmentSelection: controller.visibleEnvironmentSelection,
    effectiveEnvironmentSelection: controller.effectiveEnvironmentSelection,
    environmentSelectionPending: controller.environmentSelectionPending,
    onEnvironmentSelectionChange: controller.updateEnvironmentSelection,
    hasControlledEnvironmentSelection:
      controller.hasControlledEnvironmentSelection,
  }

  return (
    <main
      className={cn(
        "flex h-full min-h-0 min-w-0 flex-col bg-background",
        className,
      )}
      data-testid="agent-workbench"
    >
      {controller.effectiveSessionId ? (
        sessionState ? (
          <SessionWorkbench
            key={controller.effectiveSessionId}
            sessionId={controller.effectiveSessionId}
            state={sessionState}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            headerActions={headerActions}
            {...common}
          />
        ) : (
          <LiveSessionWorkbench
            key={controller.effectiveSessionId}
            sessionId={controller.effectiveSessionId}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            headerActions={headerActions}
            {...common}
          />
        )
      ) : (
        <DraftWorkbench
          permissionMode={controller.draftPermissionMode}
          workspaceAccess={controller.draftWorkspaceAccess}
          draftSessionId={controller.draftSessionId}
          onPermissionModeChange={controller.updateDraftPermissionMode}
          headerActions={headerActions}
          starterPrompts={starterPrompts}
          {...common}
        />
      )}
      <AgentModelConnectionDialog
        open={controller.modelConnectionOpen}
        onOpenChange={controller.setModelConnectionOpen}
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
  onOpenRun?: (runId: string) => void
  conversationModelControls?: ReactNode
  environmentTargets: readonly AgentEnvironmentTarget[]
  environmentSelection: AgentEnvironmentSelection
  effectiveEnvironmentSelection: AgentEnvironmentSelection
  environmentSelectionPending: boolean
  onEnvironmentSelectionChange: (
    selection: AgentEnvironmentSelection,
  ) => Promise<void>
  hasControlledEnvironmentSelection: boolean
}

function DraftWorkbench({
  permissionMode,
  workspaceAccess,
  draftSessionId,
  onPermissionModeChange,
  headerActions,
  starterPrompts,
  ...shared
}: SharedWorkbenchProps & {
  permissionMode: AgentPermissionMode
  workspaceAccess: AgentWorkspaceAccess
  draftSessionId: string | null
  onPermissionModeChange: (mode: AgentPermissionMode) => Promise<void>
  headerActions?: ReactNode
  starterPrompts?: readonly string[]
}) {
  const t = useTranslations("agentWorkbench")
  const locale = useLocale()
  const [error, setError] = useState<string | null>(null)
  const { models, selectedModel, setSelectedModel, isLoading } =
    useLlmSettings()
  const generatedStarterPrompts = useAgentStarterPrompts(
    shared.projectId,
    locale,
  )
  const fallbackStarterPrompts = [
    t("starterPrompts.reviewRun"),
    t("starterPrompts.explainInputs"),
    t("starterPrompts.checkWorkflow"),
  ]
  const ensureSession = shared.ensureSession
  const ensureDraftSession = useCallback(() => {
    const modelSelector: DraftModelSelector | undefined = selectedModel
      ? selectedModel.model_id
        ? { modelId: selectedModel.model_id }
        : selectedModel.provider && selectedModel.model
          ? { provider: selectedModel.provider, model: selectedModel.model }
          : undefined
      : undefined
    return ensureSession(modelSelector)
  }, [ensureSession, selectedModel])

  const updateDraftModelSelection = useCallback(
    async (selection: ModelSelection | null) => {
      await setSelectedModel(selection)
      if (!draftSessionId || !selection) return
      const model = selection.model_id
        ? { modelId: selection.model_id }
        : selection.provider && selection.model
          ? { provider: selection.provider, model: selection.model }
          : null
      if (!model) return

      const snapshot = await updateAgentSession(draftSessionId, {
        model,
      })
      publishAgentSessionSummary(sessionSummaryFromView(snapshot.session))
    },
    [draftSessionId, setSelectedModel],
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
        className="relative flex min-h-0 flex-1 flex-col items-center justify-center overflow-y-auto px-2 py-12 sm:px-6"
      >
        <div
          aria-hidden="true"
          className="pointer-events-none absolute left-1/2 top-1/2 h-80 w-[min(90vw,54rem)] -translate-x-1/2 -translate-y-1/2 rounded-full bg-foreground/[0.025] blur-3xl dark:bg-foreground/[0.018]"
        />
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
              onSelectModel={(selection) =>
                void updateDraftModelSelection(selection)
              }
              disabled={isLoading}
              variant="composer"
            />
          }
          environmentTargets={shared.environmentTargets}
          environmentSelection={shared.environmentSelection}
          effectiveEnvironmentSelection={shared.effectiveEnvironmentSelection}
          environmentSelectionPending={shared.environmentSelectionPending}
          onEnvironmentSelectionChange={shared.onEnvironmentSelectionChange}
          capabilityHint={t("capabilityHint")}
          starterPrompts={
            starterPrompts ??
            (generatedStarterPrompts.prompts.length > 0
              ? generatedStarterPrompts.prompts
              : fallbackStarterPrompts)
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
  const [environmentUpdate, setEnvironmentUpdate] = useState<{
    selection: AgentEnvironmentSelection
  } | null>(null)

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
          <CircleAlert
            aria-hidden="true"
            className="mx-auto text-destructive"
          />
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

  const conversationView = state.conversationView

  const effectiveEnvironmentSelection = environmentSelectionFromSession(
    state.session,
  )
  const visibleEnvironmentUpdate =
    environmentUpdate &&
    !environmentSelectionEquals(
      environmentUpdate.selection,
      effectiveEnvironmentSelection,
    )
      ? environmentUpdate
      : null
  const requestedEnvironmentSelection = shared.hasControlledEnvironmentSelection
    ? shared.environmentSelection
    : (visibleEnvironmentUpdate?.selection ?? effectiveEnvironmentSelection)
  const confirmedEnvironmentSelection = shared.hasControlledEnvironmentSelection
    ? shared.effectiveEnvironmentSelection
    : effectiveEnvironmentSelection
  const environmentSelectionPending = shared.hasControlledEnvironmentSelection
    ? shared.environmentSelectionPending
    : visibleEnvironmentUpdate !== null

  const updateLiveEnvironmentSelection = async (
    selection: AgentEnvironmentSelection,
  ) => {
    if (shared.hasControlledEnvironmentSelection) {
      await shared.onEnvironmentSelectionChange(selection)
      return
    }
    setEnvironmentUpdate({ selection })
    try {
      await state.updateEnvironmentScope(environmentScopeFromSelection(selection))
    } catch (error) {
      setEnvironmentUpdate(null)
      throw error
    }
  }

  const isEmpty =
    conversationView !== null &&
    conversationView.transcript.length === 0 &&
    conversationView.activeWork === null
  return (
    <>
      <ConversationHeader
        title={state.session.title || t("untitled")}
        model={state.session.model.display_name}
        connectionStatus={state.connectionStatus}
        actions={headerActions}
      />
      {isEmpty ? (
        <AgentEmptyState />
      ) : conversationView ? (
        <ConversationTranscript
          className="flex-1"
          view={conversationView}
          onRespond={interactive ? state.respond : undefined}
          onOpenRun={shared.onOpenRun}
        />
      ) : state.isLoading ? (
        <WorkbenchSkeleton />
      ) : (
        <ConversationViewUnavailable onRetry={state.retry} />
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
        modelControls={
          shared.conversationModelControls ?? (
            <SessionModelSelector
              session={state.session}
              activeRun={state.activeRun !== null}
              disabled={!interactive || state.session.status !== "active"}
              onChange={state.updateModel}
            />
          )
        }
        environmentTargets={shared.environmentTargets}
        environmentSelection={requestedEnvironmentSelection}
        effectiveEnvironmentSelection={confirmedEnvironmentSelection}
        environmentSelectionPending={environmentSelectionPending}
        onEnvironmentSelectionChange={updateLiveEnvironmentSelection}
      />
    </>
  )
}

function ConversationViewUnavailable({ onRetry }: { onRetry: () => void }) {
  const t = useTranslations("agentWorkbench")
  return (
    <div className="grid min-h-0 flex-1 place-items-center px-6 text-center">
      <div className="flex max-w-sm flex-col items-center gap-3">
        <CircleAlert aria-hidden="true" className="text-destructive" />
        <h2 className="text-base font-medium">{t("loadErrorTitle")}</h2>
        <p className="text-sm text-muted-foreground">
          {t("loadErrorDescription")}
        </p>
        <Button type="button" variant="outline" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          {t("retry")}
        </Button>
      </div>
    </div>
  )
}

function ConversationHeader({
  title,
  model,
  connectionStatus,
  actions,
}: {
  title: string
  model: string
  connectionStatus?:
    "connecting" | "connected" | "reconnecting" | "disconnected"
  actions?: ReactNode
}) {
  const t = useTranslations("agentWorkbench")
  const showConnection = connectionStatus && connectionStatus !== "connected"
  const ConnectionIcon =
    connectionStatus === "reconnecting" || connectionStatus === "disconnected"
      ? WifiOff
      : Loader2
  return (
    <header className="flex min-h-12 min-w-0 items-center gap-3 border-b border-border/70 px-4 py-1.5">
      <Bot aria-hidden="true" className="shrink-0 text-muted-foreground" />
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-sm font-medium leading-5">{title}</h1>
        <p
          data-testid="agent-header-model"
          className="truncate text-[11px] leading-4 text-muted-foreground"
        >
          {model}
        </p>
      </div>
      {showConnection ? (
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
          <span className="hidden sm:inline">
            {t(`connection.${connectionStatus}`)}
          </span>
        </span>
      ) : null}
      {actions}
    </header>
  )
}

function AgentEmptyState({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("agentWorkbench")
  return (
    <div
      className={cn(
        "relative grid place-items-center px-6 text-center",
        compact ? "pb-7" : "min-h-0 flex-1 py-10",
      )}
    >
      <div className="max-w-xl">
        <Bot
          aria-hidden="true"
          className="mx-auto mb-4 size-6 text-muted-foreground/65"
        />
        <h2
          className={cn(
            "text-balance font-semibold tracking-[-0.025em]",
            compact ? "text-2xl sm:text-[1.75rem]" : "text-base",
          )}
        >
          {t("emptyTitle")}
        </h2>
        <p className="mt-2 text-pretty text-sm leading-6 text-muted-foreground">
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

function SessionModelSelector({
  session,
  activeRun,
  disabled,
  onChange,
}: {
  session: SessionView
  activeRun: boolean
  disabled: boolean
  onChange: AgentSessionState["updateModel"]
}) {
  const t = useTranslations("agentComposer")
  const { models, isLoading } = useLlmSettings()
  const effectiveSelection = modelSelectionFromSession(session, models)
  const [update, setUpdate] = useState<{
    selection: ModelSelection
    state: "pending" | "error"
  } | null>(null)
  const visibleUpdate =
    update && !modelSelectionEquals(update.selection, effectiveSelection)
      ? update
      : null
  const selectedModel =
    visibleUpdate?.state === "pending"
      ? visibleUpdate.selection
      : effectiveSelection
  const pending = visibleUpdate?.state === "pending"

  const requestChange = async (selection: ModelSelection | null) => {
    if (!selection?.model_id && (!selection?.provider || !selection.model)) return
    setUpdate({ selection, state: "pending" })
    try {
      await onChange(
        selection.model_id
          ? { modelId: selection.model_id }
          : { provider: selection.provider!, model: selection.model! },
      )
    } catch {
      setUpdate({ selection, state: "error" })
    }
  }

  return (
    <div className="flex min-w-0 flex-col items-start gap-1.5">
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        onSelectModel={(selection) => void requestChange(selection)}
        disabled={disabled || isLoading || pending}
        variant="composer"
      />
      {pending ? (
        <p role="status" className="px-2 text-[11px] text-muted-foreground">
          {t("model.updating")}
        </p>
      ) : activeRun ? (
        <p className="px-2 text-[11px] text-muted-foreground">
          {t("permission.nextRun")}
        </p>
      ) : null}
      {visibleUpdate?.state === "error" ? (
        <div
          role="alert"
          className="flex items-center gap-1 px-2 text-[11px] text-destructive"
        >
          <span>{t("model.updateError")}</span>
          <Button
            type="button"
            variant="link"
            size="sm"
            className="h-auto px-1 text-[11px]"
            onClick={() => void requestChange(visibleUpdate.selection)}
          >
            {t("model.retry")}
          </Button>
        </div>
      ) : null}
    </div>
  )
}

function modelSelectionFromSession(
  session: SessionView,
  models: ReturnType<typeof useLlmSettings>["models"],
): ModelSelection {
  const directProvider = models.find(
    (group) =>
      group.provider === session.model.provider &&
      group.models.some((candidate) => candidate.id === session.model.model),
  )
  const compatibleProviders = models.filter(
    (group) =>
      group.provider_kind === session.model.provider &&
      group.models.some((candidate) => candidate.id === session.model.model),
  )
  const provider =
    directProvider ??
    (compatibleProviders.length === 1 ? compatibleProviders[0] : undefined)
  const model = provider?.models.find(
    (candidate) => candidate.id === session.model.model,
  )
  return {
    provider: provider?.provider ?? session.model.provider,
    model: session.model.model,
    model_id: model?.model_id ?? null,
  }
}

function modelSelectionEquals(
  left: ModelSelection,
  right: ModelSelection,
) {
  if (left.model_id && right.model_id) return left.model_id === right.model_id
  return left.provider === right.provider && left.model === right.model
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
