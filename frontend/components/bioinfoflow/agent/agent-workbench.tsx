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

import {
  AgentCommandDiscoveryHint,
  AgentComposer,
} from "@/components/bioinfoflow/agent/agent-composer"
import type {
  AgentEnvironmentSelection,
  AgentEnvironmentTarget,
} from "@/components/bioinfoflow/agent/environment-selector"
import { AgentContextPicker } from "@/components/bioinfoflow/agent/agent-context-picker"
import { AgentModelConnectionDialog } from "@/components/bioinfoflow/agent/agent-model-connection-dialog"
import { AgentTracePanel } from "@/components/bioinfoflow/agent/agent-trace-view"
import { ConversationTranscript } from "@/components/bioinfoflow/agent/conversation-transcript"
import { AgentPlanCard } from "@/components/bioinfoflow/agent/plan-entry"
import { useAgentTranscriptArtifacts } from "@/components/bioinfoflow/agent/use-agent-transcript-artifacts"
import {
  environmentSelectionEquals,
  useAgentWorkbenchController,
  type DraftModelSelector,
} from "@/components/bioinfoflow/agent/use-agent-workbench-controller"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Alert, AlertTitle } from "@/components/ui/alert"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import {
  useAgentSession,
} from "@/hooks/use-agent-session"
import { useAgentStarterPrompts } from "@/hooks/use-agent-starter-prompts"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import type { ModelSelection } from "@/hooks/use-llm-settings"
import {
  catalogModelSelectionEquals,
  catalogModelSelectionFromConversation,
  conversationModelSelectionFromCatalog,
} from "@/lib/agent/conversation-model/model-catalog-adapter"
import type { AgentContextInput } from "@/lib/agent/context"
import type {
  ComposerInputPart,
  ConversationCommandPorts,
  ConversationModelSelection,
  ConversationPermissionMode,
  ConversationSessionBinding,
  ConversationSettings,
  ConversationSummary,
  ConversationWorkspaceAccess,
} from "@/lib/agent/conversation-model/types"
import {
  publishConversationSummary,
} from "@/lib/agent/session-preferences"
import { ApiError } from "@/lib/api"
import {
  bioinfoFlowAgentWorkspaceAdapter,
  type AgentWorkspaceAdapter,
} from "@/lib/agent/workspace-adapter"
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
  /** Stable Conversation binding injected by demo adapters and tests. */
  sessionState?: ConversationSessionBinding
  interactive?: boolean
  onActiveSessionIdChange?: (sessionId: string) => void
  onBeforeSessionRoute?: (sessionId: string) => void
  onSessionResolved?: (session: ConversationSummary) => void
  onOpenRun?: (runId: string) => void
  onOpenArtifact?: (artifactId: string) => void
  workspaceAdapter?: AgentWorkspaceAdapter
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
    onBeforeSessionRoute,
    onSessionResolved,
    onOpenRun,
    onOpenArtifact,
    workspaceAdapter = bioinfoFlowAgentWorkspaceAdapter,
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
    onBeforeSessionRoute,
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
    updateDraftModel: controller.updateDraftModel,
    sendDraftMessage: controller.sendDraftMessage,
    onOpenRun,
    onOpenArtifact,
    workspaceAdapter,
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
        "relative flex h-full min-h-0 min-w-0 flex-col bg-background",
        className,
      )}
      data-testid="agent-workbench"
    >
      {controller.effectiveSessionId ? (
        sessionState ? (
          <SessionWorkbench
            key={controller.effectiveSessionId}
            sessionId={controller.effectiveSessionId}
            binding={sessionState}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            {...common}
          />
        ) : (
          <LiveSessionWorkbench
            key={controller.effectiveSessionId}
            sessionId={controller.effectiveSessionId}
            interactive={interactive}
            onSessionResolved={onSessionResolved}
            {...common}
          />
        )
      ) : (
        <DraftWorkbench
          permissionMode={controller.draftPermissionMode}
          workspaceAccess={controller.draftWorkspaceAccess}
          draftSessionId={controller.draftSessionId}
          onPermissionModeChange={controller.updateDraftPermissionMode}
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
  sendDraftMessage: (
    parts: ComposerInputPart[],
    model?: ConversationModelSelection,
  ) => Promise<string>
  updateDraftModel: (model: ConversationModelSelection | null) => Promise<void>
  routeToSession: (sessionId: string) => void
  textareaRef: RefObject<HTMLTextAreaElement | null>
  setCancelHandler: (handler: (() => Promise<void>) | null) => void
  setModelConnectionOpen: (open: boolean) => void
  onOpenRun?: (runId: string) => void
  onOpenArtifact?: (artifactId: string) => void
  workspaceAdapter: AgentWorkspaceAdapter
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
  starterPrompts,
  ...shared
}: SharedWorkbenchProps & {
  permissionMode: ConversationPermissionMode
  workspaceAccess: ConversationWorkspaceAccess
  draftSessionId: string | null
  onPermissionModeChange: (mode: ConversationPermissionMode) => Promise<void>
  starterPrompts?: readonly string[]
}) {
  const t = useTranslations("agentWorkbench")
  const locale = useLocale()
  const [error, setError] = useState<string | null>(null)
  const [draftEmpty, setDraftEmpty] = useState(true)
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
  const updateDraftModel = shared.updateDraftModel
  const sendDraftMessage = shared.sendDraftMessage
  const ensureDraftSession = useCallback(() => {
    const modelSelector = conversationModelSelectionFromCatalog(selectedModel)
  return ensureSession(
      modelSelector
        ? "modelId" in modelSelector
          ? { modelId: modelSelector.modelId }
          : { provider: modelSelector.provider, model: modelSelector.model }
        : undefined,
    )
  }, [ensureSession, selectedModel])

  const updateDraftModelSelection = useCallback(
    async (selection: ModelSelection | null) => {
      await setSelectedModel(selection)
      await updateDraftModel(conversationModelSelectionFromCatalog(selection))
    },
    [setSelectedModel, updateDraftModel],
  )

  const send = async (parts: ComposerInputPart[]) => {
    setError(null)
    shared.setModelConnectionOpen(false)
    try {
      const sessionId = await sendDraftMessage(
        parts,
        conversationModelSelectionFromCatalog(selectedModel) ?? undefined,
      )
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
      <div
        data-testid="agent-draft-entry"
        className="relative flex min-h-0 flex-1 items-center justify-center overflow-hidden bg-background px-4 py-8"
      >
        <div
          data-testid="agent-draft-stage"
          className="agent-center-stage relative w-full max-w-[42rem] -translate-y-8"
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
            starterPrompts={
              starterPrompts ??
              (generatedStarterPrompts.prompts.length > 0
                ? generatedStarterPrompts.prompts
                : fallbackStarterPrompts)
            }
            renderCommandDiscoveryHint={false}
            onDraftEmptyChange={setDraftEmpty}
          />
        </div>
        <AgentCommandDiscoveryHint visible={draftEmpty} />
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
  onSessionResolved?: (session: ConversationSummary) => void
}) {
  const state = useAgentSession(sessionId)
  return <SessionWorkbench sessionId={sessionId} binding={state} {...props} />
}

function SessionWorkbench({
  sessionId,
  binding,
  interactive,
  onSessionResolved,
  ...shared
}: SharedWorkbenchProps & {
  sessionId: string
  binding: ConversationSessionBinding
  interactive: boolean
  onSessionResolved?: (session: ConversationSummary) => void
}) {
  const t = useTranslations("agentWorkbench")
  const setCancelHandler = shared.setCancelHandler
  const [environmentUpdate, setEnvironmentUpdate] = useState<{
    selection: AgentEnvironmentSelection
  } | null>(null)
  const [activeView, setActiveView] = useState<"conversation" | "trace">(
    "conversation",
  )

  useEffect(() => {
    setCancelHandler(interactive ? binding.commands.cancel : null)
    return () => {
      setCancelHandler(null)
    }
  }, [interactive, setCancelHandler, binding.commands.cancel])

  const view = binding.view ?? null

  const supplementalArtifacts = useAgentTranscriptArtifacts({
    adapter: shared.workspaceAdapter,
    sessionId,
    projectId: shared.projectId,
    view,
  })

  useEffect(() => {
    if (!view) return
    publishConversationSummary(view.conversation)
    onSessionResolved?.(view.conversation)
  }, [view, onSessionResolved])

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

  const sendMessage = async (parts: ComposerInputPart[]) => {
    await runSessionCommand(() => binding.commands.sendMessage(parts))
    shared.setContextInputs([])
    shared.routeToSession(sessionId)
  }
  const steer = async (parts: ComposerInputPart[]) => {
    await runSessionCommand(() => binding.commands.steer(parts))
    shared.setContextInputs([])
  }

  if (binding.isLoading && !view) return <WorkbenchSkeleton />

  const effectiveEnvironmentSelection = view
    ? environmentSelectionFromSettings(view.composer.settings)
    : { mode: "auto" as const }
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
      await binding.commands.updateEnvironmentScope(
        conversationEnvironmentScopeFromSelection(selection),
      )
    } catch (error) {
      setEnvironmentUpdate(null)
      throw error
    }
  }

  const isEmpty =
    view !== null &&
    view.transcript.length === 0 &&
    view.activeWork === null
  return (
    <>
      <ConversationConnectionStatus connectionStatus={binding.connectionStatus} />
      <Tabs
        value={activeView}
        onValueChange={(value) =>
          setActiveView(value as "conversation" | "trace")
        }
        className="min-h-0 flex-1 gap-0"
      >
        <div className="flex h-10 shrink-0 items-center border-b border-border/70 px-4">
          <TabsList className="h-8 gap-4 rounded-none bg-transparent p-0">
            <TabsTrigger
              value="conversation"
              className="h-8 rounded-none border-0 border-b-2 border-transparent px-0 text-xs font-medium text-muted-foreground shadow-none data-[state=active]:border-foreground/65 data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
            >
              {t("views.conversation")}
            </TabsTrigger>
            <TabsTrigger
              value="trace"
              className="h-8 rounded-none border-0 border-b-2 border-transparent px-0 text-xs font-medium text-muted-foreground shadow-none data-[state=active]:border-foreground/65 data-[state=active]:bg-transparent data-[state=active]:text-foreground data-[state=active]:shadow-none"
            >
              {t("views.trace")}
            </TabsTrigger>
          </TabsList>
        </div>

        <TabsContent
          forceMount
          value="conversation"
          className="m-0 flex min-h-0 flex-1 flex-col data-[state=inactive]:hidden"
        >
          {isEmpty ? (
            <AgentEmptyState />
          ) : view ? (
            <ConversationTranscript
              className="flex-1"
              view={view}
              onRespond={interactive ? binding.commands.respond : undefined}
              onOpenRun={shared.onOpenRun}
              onOpenArtifact={shared.onOpenArtifact}
              supplementalArtifacts={supplementalArtifacts}
            />
          ) : binding.isLoading ? (
            <WorkbenchSkeleton />
          ) : (
            <ConversationViewUnavailable
              message={binding.error?.message}
              onRetry={binding.commands.retry}
            />
          )}
          {view && view.conversation.status !== "active" ? (
            <p
              role="status"
              className="border-t border-border/70 bg-muted/25 px-4 py-2 text-center text-xs leading-5 text-muted-foreground"
            >
              {t(`readOnly.${view.conversation.status}`)}
            </p>
          ) : null}
          {view?.currentPlan ? (
            <div className="relative z-10 flex shrink-0 justify-center px-4 pb-2">
              <AgentPlanCard plan={view.currentPlan} />
            </div>
          ) : null}
          <AgentComposer
            placement="dock"
            permissionMode={view?.composer.settings.permissionMode ?? "ask_dangerous"}
            workspaceAccess={view?.composer.settings.workspaceAccess ?? "read_write"}
            activeRun={view?.activeWork ?? null}
            onSendMessage={sendMessage}
            onSteer={steer}
            onCancel={binding.commands.cancel}
            onPermissionModeChange={binding.commands.updatePermissionMode}
            contextInputs={shared.contextInputs}
            onRemoveContextInput={shared.removeContextInput}
            onContextSubmitted={() => shared.setContextInputs([])}
            textareaRef={shared.textareaRef}
            disabled={!interactive || view?.conversation.status !== "active"}
            contextControls={
              <AgentContextPicker
                projectId={view?.conversation.projectId ?? null}
                sessionId={sessionId}
                ensureSession={shared.ensureSession}
                onAdd={shared.addContextInput}
                disabled={!interactive || view?.conversation.status !== "active"}
              />
            }
            modelControls={
              shared.conversationModelControls ?? (
                <SessionModelSelector
                  model={view?.composer.settings.model ?? null}
                  disabled={!interactive || view?.conversation.status !== "active"}
                  onChange={binding.commands.updateModel}
                />
              )
            }
            environmentTargets={shared.environmentTargets}
            environmentSelection={requestedEnvironmentSelection}
            effectiveEnvironmentSelection={confirmedEnvironmentSelection}
            environmentSelectionPending={environmentSelectionPending}
            onEnvironmentSelectionChange={updateLiveEnvironmentSelection}
          />
        </TabsContent>

        <TabsContent
          value="trace"
          className="m-0 min-h-0 flex-1"
        >
          <AgentTracePanel sessionId={sessionId} />
        </TabsContent>
      </Tabs>
    </>
  )
}

function ConversationViewUnavailable({
  message,
  onRetry,
}: {
  message?: string
  onRetry: () => void
}) {
  const t = useTranslations("agentWorkbench")
  return (
    <div className="grid min-h-0 flex-1 place-items-center px-6 text-center">
      <div className="flex max-w-sm flex-col items-center gap-3">
        <CircleAlert aria-hidden="true" className="text-destructive" />
        <h2 className="text-base font-medium">{t("loadErrorTitle")}</h2>
        <p className="text-sm text-muted-foreground">
          {message ?? t("loadErrorDescription")}
        </p>
        <Button type="button" variant="outline" onClick={onRetry}>
          <RefreshCw data-icon="inline-start" aria-hidden="true" />
          {t("retry")}
        </Button>
      </div>
    </div>
  )
}

function ConversationConnectionStatus({
  connectionStatus,
}: {
  connectionStatus?:
    "connecting" | "connected" | "reconnecting" | "disconnected"
}) {
  const t = useTranslations("agentWorkbench")
  const showConnection = connectionStatus && connectionStatus !== "connected"
  if (!showConnection) return null
  const ConnectionIcon =
    connectionStatus === "reconnecting" || connectionStatus === "disconnected"
      ? WifiOff
      : Loader2
  return (
    <div className="flex shrink-0 justify-end px-3 pt-3">
      <div
        role="status"
        className="pointer-events-none flex items-center gap-1.5 rounded-full border border-border/60 bg-background/90 px-2.5 py-1 text-xs text-muted-foreground backdrop-blur-sm"
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
      </div>
    </div>
  )
}

function AgentEmptyState({ compact = false }: { compact?: boolean }) {
  const t = useTranslations("agentWorkbench")
  if (compact) {
    return (
      <h1 className="mb-4 text-balance text-center text-[18px] font-medium tracking-[-0.015em] text-foreground/80 sm:text-[19px]">
        {t("emptyTitle")}
      </h1>
    )
  }

  return (
    <div
      className="relative grid min-h-0 flex-1 place-items-center px-6 py-10 text-center"
    >
      <div className="max-w-xl">
        <Bot
          aria-hidden="true"
          className="mx-auto mb-4 size-6 text-muted-foreground/65"
        />
        <h2 className="text-balance text-base font-semibold tracking-[-0.025em]">
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
  model,
  disabled,
  onChange,
}: {
  model: ConversationSettings["model"] | null
  disabled: boolean
  onChange: ConversationCommandPorts["updateModel"]
}) {
  const t = useTranslations("agentComposer")
  const { models, isLoading } = useLlmSettings()
  const effectiveSelection = catalogModelSelectionFromConversation(model, models)
  const [update, setUpdate] = useState<{
    selection: ModelSelection
    state: "pending" | "error"
  } | null>(null)
  const visibleUpdate =
    update && !catalogModelSelectionEquals(update.selection, effectiveSelection)
      ? update
      : null
  const selectedModel =
    visibleUpdate?.state === "pending"
      ? visibleUpdate.selection
      : effectiveSelection
  const pending = visibleUpdate?.state === "pending"

  const requestChange = async (selection: ModelSelection | null) => {
    const modelSelection = conversationModelSelectionFromCatalog(selection)
    if (!selection || !modelSelection) return
    setUpdate({ selection, state: "pending" })
    try {
      await onChange(modelSelection)
    } catch {
      setUpdate({ selection, state: "error" })
    }
  }

  const feedback = pending ? (
    <p role="status">{t("model.updating")}</p>
  ) : visibleUpdate?.state === "error" ? (
    <div role="alert" className="flex items-center gap-1 text-destructive">
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
  ) : null

  return (
    <ModelSelector
      models={models}
      selectedModel={selectedModel}
      onSelectModel={(selection) => void requestChange(selection)}
      disabled={disabled || isLoading || pending}
      variant="composer"
      feedback={feedback}
    />
  )
}


function environmentSelectionFromSettings(
  settings: ConversationSettings,
): AgentEnvironmentSelection {
  return settings.environmentScope.mode === "manual"
    ? {
        mode: "manual",
        targetIds: settings.environmentScope.environmentIds,
      }
    : { mode: "auto" }
}

function conversationEnvironmentScopeFromSelection(
  selection: AgentEnvironmentSelection,
) {
  return selection.mode === "manual"
    ? { mode: "manual" as const, environmentIds: selection.targetIds }
    : { mode: "auto" as const }
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
