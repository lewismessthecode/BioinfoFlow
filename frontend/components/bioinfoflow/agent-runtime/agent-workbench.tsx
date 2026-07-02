"use client"

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react"
import { PanelRightClose, PanelRightOpen, SlidersHorizontal } from "lucide-react"
import { useTranslations } from "next-intl"

import { AgentComposer } from "./agent-composer"
import { AgentEnvironmentCard } from "./agent-environment-card"
import { AgentTabbedPanel, type AgentTabbedPanelTab } from "./agent-tabbed-panel"
import { AgentTodoDock } from "./agent-todo-dock"
import { AgentTranscript } from "./agent-transcript"
import { ComposerApprovalPopover } from "./composer-approval-popover"
import { todosFromArtifact } from "./artifact-viewers"
import { Button } from "@/components/ui/button"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { useIsMobile } from "@/hooks/use-media-query"
import {
  buildAgentRuntimeTimeline,
  deriveTodoDisplayItems,
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeFileRefPart,
  type AgentRuntimeInputPart,
  type AgentRuntimeTurn,
} from "@/lib/agent-runtime"
import {
  readAgentTurnPolicy,
  type AgentTurnPolicy,
} from "@/lib/agent-runtime/turn-policy"
import { cn } from "@/lib/utils"

export type AgentWorkbenchHandle = {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

type AgentWorkbenchProps = {
  projectId?: string | null
  activeSessionId?: string | null
  onActiveSessionIdChange?: (sessionId: string) => void
  workspaceEnabled?: boolean
  className?: string
}

export const AgentWorkbench = forwardRef<AgentWorkbenchHandle, AgentWorkbenchProps>(
  function AgentWorkbench(
    {
      projectId,
      activeSessionId,
      onActiveSessionIdChange,
      workspaceEnabled = true,
      className,
    },
    ref,
  ) {
    const t = useTranslations("agentRuntime")
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const isMobile = useIsMobile()
    const [input, setInput] = useState("")
    const [contextAttachments, setContextAttachments] = useState<AgentRuntimeFileRefPart[]>([])
    const [remoteConnectionOverride, setRemoteConnectionOverride] = useState<{
      sessionId: string
      value: string
    } | null>(null)
    const [hasSubmittedDraft, setHasSubmittedDraft] = useState(false)
    const [optimisticTurn, setOptimisticTurn] = useState<AgentRuntimeTurn | null>(null)
    const [turnPolicy] = useState<AgentTurnPolicy>(readAgentTurnPolicy)
    const [queuedSubmission, setQueuedSubmission] = useState<{
      text: string
      inputParts: AgentRuntimeInputPart[]
      modelSelection: typeof selectedModel
      optimisticTurn: AgentRuntimeTurn
    } | null>(null)
    const [environmentOpen, setEnvironmentOpen] = useState(false)
    const [sidecarOpen, setSidecarOpen] = useState(false)
    const [activeSidecarTab, setActiveSidecarTab] = useState<AgentTabbedPanelTab>("files")
    const [browserInput, setBrowserInput] = useState("")
    const [browserSrc, setBrowserSrc] = useState("")
    const [artifactState, setArtifactState] = useState<{
      sessionId: string
      artifacts: AgentRuntimeArtifact[]
    } | null>(null)
    const workspaceShell = useOptionalWorkspaceShell()
    const setNavbarActions = workspaceShell?.setNavbarActions
    const { models, selectedModel, isLoading: modelsLoading, setSelectedModel } =
      useLlmSettings()
    const {
      state,
      eventWindowLimited,
      mode,
      setMode,
      permissionMode,
      setPermissionMode,
      setActiveSessionId,
      send,
      interrupt,
      decideAction,
    } = useAgentRuntime(projectId, {
      activeSessionId,
      onActiveSessionIdChange,
    })
    const agentMode = mode ?? "execution"
    const sessionId = state.session?.id ?? ""
    const sessionRemoteConnectionId = getSessionRemoteConnectionId(state.session?.metadata)
    const projectRemoteConnectionId = useMemo(() => {
      if (!projectId) return ""
      const project = workspaceShell?.projects.find((item) => item.id === projectId)
      if (project?.storage_mode !== "remote") return ""
      return typeof project.remote_connection_id === "string"
        ? project.remote_connection_id
        : ""
    }, [projectId, workspaceShell?.projects])
    const hasRemoteConnectionOverride =
      remoteConnectionOverride?.sessionId === sessionId
    const selectedRemoteConnectionId =
      hasRemoteConnectionOverride
        ? remoteConnectionOverride.value
        : sessionRemoteConnectionId || (state.session ? "" : projectRemoteConnectionId)

    const disabled = !workspaceEnabled
    const visibleOptimisticTurn =
      optimisticTurn && !state.turns.some((turn) => turn.id === optimisticTurn.id)
        ? optimisticTurn
        : null
    const transcriptTimeline = useMemo(
      () =>
        visibleOptimisticTurn
          ? buildAgentRuntimeTimeline(
              [...state.turns, visibleOptimisticTurn],
              state.events,
            )
          : state.timeline,
      [state.events, state.timeline, state.turns, visibleOptimisticTurn],
    )
    const hasTurns = state.turns.length > 0 || Boolean(visibleOptimisticTurn)
    const hasSelectedSession = Boolean(activeSessionId || state.session?.id)
    const hasConversation = hasTurns || hasSubmittedDraft || hasSelectedSession
    const isRunning = state.status === "running"
    const hasActiveTurn =
      isRunning ||
      state.turns.some(
        (turn) => turn.status === "queued" || turn.status === "running",
      )
    const artifactEventCount = useMemo(
      () => state.events.filter((event) => event.type === "artifact.created").length,
      [state.events],
    )
    const transcriptArtifacts = useMemo(
      () =>
        artifactState && artifactState.sessionId === state.session?.id
          ? artifactState.artifacts
          : [],
      [artifactState, state.session?.id],
    )
    const latestTurnId = state.timeline.at(-1)?.turn.id ?? null
    const latestTodoArtifact = useMemo(() => {
      if (!latestTurnId) return undefined
      return [...transcriptArtifacts]
        .filter((artifact) => artifact.type === "todo_list" && artifact.turn_id === latestTurnId)
        .sort((a, b) => (a.created_at < b.created_at ? 1 : -1))[0]
    }, [latestTurnId, transcriptArtifacts])
    const todoTurn = latestTodoArtifact
      ? state.timeline.find((entry) => entry.turn.id === latestTodoArtifact.turn_id)?.turn ?? null
      : null
    const todoDisplayItems = useMemo(
      () =>
        latestTodoArtifact
          ? deriveTodoDisplayItems(todosFromArtifact(latestTodoArtifact), todoTurn)
          : [],
      [latestTodoArtifact, todoTurn],
    )
    // The side panel is now secondary detail. Approvals surface inline and above
    // the composer, so pending decisions no longer force the drawer open.
    const desktopSidecarVisible = sidecarOpen && !isMobile
    const mobileSidecarVisible = sidecarOpen && isMobile
    const sidecarLabel = desktopSidecarVisible || mobileSidecarVisible
      ? t("sidecar.collapse")
      : t("sidecar.expand")
    const environmentLabel = environmentOpen
      ? t("environment.close")
      : t("environment.open")

    useImperativeHandle(
      ref,
      () => ({
        focusInput: () => textareaRef.current?.focus(),
        stop: () => {
          void interrupt()
        },
        newConversation: () => {
          setActiveSessionId(null)
          setInput("")
          setContextAttachments([])
          setRemoteConnectionOverride(null)
          setHasSubmittedDraft(false)
          setOptimisticTurn(null)
          setEnvironmentOpen(false)
          setSidecarOpen(false)
          setActiveSidecarTab("files")
          setBrowserInput("")
          setBrowserSrc("")
        },
      }),
      [interrupt, setActiveSessionId],
    )

    useEffect(() => {
      const sessionId = state.session?.id
      if (!sessionId) return
      let cancelled = false
      void listAgentRuntimeSessionArtifacts(sessionId)
        .then((next) => {
          if (!cancelled) setArtifactState({ sessionId, artifacts: next })
        })
        .catch(() => {
          if (!cancelled) setArtifactState({ sessionId, artifacts: [] })
        })
      return () => {
        cancelled = true
      }
    }, [state.session?.id, artifactEventCount])

    const addContextAttachment = useCallback((path: string) => {
      const label = path.split("/").pop() || path
      setContextAttachments((current) => {
        if (current.some((attachment) => attachment.path === path)) return current
        return [...current, { kind: "file_ref", path, label, includeContent: true }]
      })
    }, [])

    const removeContextAttachment = useCallback((path: string) => {
      setContextAttachments((current) =>
        current.filter((attachment) => attachment.path !== path),
      )
    }, [])

    const handleRemoteConnectionChange = useCallback(
      (connectionId: string) => {
        setRemoteConnectionOverride({ sessionId, value: connectionId })
      },
      [sessionId],
    )

    const sendTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        modelSelection = selectedModel,
        optimisticTurnOverride?: AgentRuntimeTurn,
      ) => {
        const trimmedText = text.trim()
        if (!trimmedText) return
        setHasSubmittedDraft(true)
        const nextOptimisticTurn =
          optimisticTurnOverride ??
          createOptimisticTurn({
            text: trimmedText,
            inputParts,
            sessionId: activeSessionId || state.session?.id || "pending-session",
            projectId,
          })
        setOptimisticTurn(nextOptimisticTurn)
        void send(trimmedText, {
          modelSelection,
          inputParts,
          ...(hasRemoteConnectionOverride || selectedRemoteConnectionId || state.session
            ? { remoteConnectionId: selectedRemoteConnectionId }
            : {}),
        }).then(() => {
          setOptimisticTurn((current) =>
            current?.id === nextOptimisticTurn.id ? null : current,
          )
        })
      },
      [
        activeSessionId,
        hasRemoteConnectionOverride,
        projectId,
        selectedModel,
        selectedRemoteConnectionId,
        send,
        state.session,
      ],
    )

    const submitTurn = useCallback(
      (
        text: string,
        inputParts: AgentRuntimeInputPart[],
        modelSelection = selectedModel,
      ) => {
        const trimmedText = text.trim()
        if (!trimmedText) return
        if (!hasActiveTurn) {
          sendTurn(trimmedText, inputParts, modelSelection)
          return
        }

        if (turnPolicy === "queue") {
          const nextOptimisticTurn = createOptimisticTurn({
            text: trimmedText,
            inputParts,
            sessionId: activeSessionId || state.session?.id || "pending-session",
            projectId,
          })
          setHasSubmittedDraft(true)
          setOptimisticTurn(nextOptimisticTurn)
          setQueuedSubmission({
            text: trimmedText,
            inputParts,
            modelSelection,
            optimisticTurn: nextOptimisticTurn,
          })
          return
        }

        void (async () => {
          await interrupt()
          sendTurn(trimmedText, inputParts, modelSelection)
        })()
      },
      [
        activeSessionId,
        hasActiveTurn,
        interrupt,
        projectId,
        selectedModel,
        sendTurn,
        state.session?.id,
        turnPolicy,
      ],
    )

    useEffect(() => {
      if (!queuedSubmission || hasActiveTurn) return
      const next = queuedSubmission
      setQueuedSubmission(null)
      sendTurn(next.text, next.inputParts, next.modelSelection, next.optimisticTurn)
    }, [hasActiveTurn, queuedSubmission, sendTurn])

    const submit = () => {
      const text = input.trim()
      if (!text) return
      const inputParts: AgentRuntimeInputPart[] = [
        { type: "text", text },
        ...contextAttachments,
      ]
      submitTurn(text, inputParts, selectedModel)
      setInput("")
      setContextAttachments([])
    }

    const retryTurn = useCallback(
      (turn: AgentRuntimeTurn) => {
        const text = turn.input_text.trim()
        if (!text) return
        const inputParts =
          turn.input_parts && turn.input_parts.length
            ? turn.input_parts
            : [{ type: "text" as const, text }]
        submitTurn(text, inputParts, turn.model_selection ?? null)
      },
      [submitTurn],
    )

    const closeSidecar = useCallback(() => {
      setSidecarOpen(false)
    }, [])

    const toggleSidecar = useCallback(() => {
      if (desktopSidecarVisible || mobileSidecarVisible) {
        closeSidecar()
        return
      }
      setEnvironmentOpen(false)
      setSidecarOpen(true)
    }, [closeSidecar, desktopSidecarVisible, mobileSidecarVisible])

    const toggleEnvironment = useCallback(() => {
      setEnvironmentOpen((current) => {
        const next = !current
        if (next) setSidecarOpen(false)
        return next
      })
    }, [])

    useEffect(() => {
      if (!setNavbarActions) return

      setNavbarActions(
        <>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className={cn(
              "h-8 w-8 rounded-lg border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground",
              environmentOpen && "bg-accent text-foreground",
            )}
            onClick={toggleEnvironment}
            aria-label={environmentLabel}
          >
            <SlidersHorizontal className="h-4 w-4" />
          </Button>
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-8 w-8 rounded-lg border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"
            onClick={toggleSidecar}
            aria-label={sidecarLabel}
          >
            {desktopSidecarVisible || mobileSidecarVisible ? (
              <PanelRightClose className="h-4 w-4" />
            ) : (
              <PanelRightOpen className="h-4 w-4" />
            )}
          </Button>
        </>,
      )

      return () => setNavbarActions(null)
    }, [
      environmentLabel,
      environmentOpen,
      setNavbarActions,
      sidecarLabel,
      desktopSidecarVisible,
      mobileSidecarVisible,
      toggleEnvironment,
      toggleSidecar,
    ])

    const composer = (
      <AgentComposer
        ref={textareaRef}
        value={input}
        onChange={setInput}
        onSubmit={submit}
        onStop={() => void interrupt()}
        isRunning={isRunning}
        disabled={disabled}
        mode={agentMode}
        onModeChange={setMode ? (next) => void setMode(next) : undefined}
        permissionMode={permissionMode}
        onPermissionModeChange={
          setPermissionMode ? (next) => void setPermissionMode(next) : undefined
        }
        models={models}
        selectedModel={selectedModel}
        modelsLoading={modelsLoading}
        onSelectModel={(model) => void setSelectedModel(model)}
        contextAttachments={contextAttachments}
        onRemoveContextAttachment={removeContextAttachment}
        selectedRemoteConnectionId={selectedRemoteConnectionId}
        onRemoteConnectionChange={handleRemoteConnectionChange}
        compactControls={desktopSidecarVisible}
      />
    )

    return (
      <div className={cn("relative flex h-full min-w-0 flex-1 bg-background", className)}>
        <main
          className="relative flex min-w-0 flex-1 flex-col overflow-hidden transition-[padding,width] duration-300 ease-out"
          data-testid="agent-workbench-main"
        >
          {hasConversation ? (
            <>
              <AgentTodoDock items={todoDisplayItems} />
              <AgentTranscript
                timeline={transcriptTimeline}
                onDecision={decideAction}
                onRetryTurn={retryTurn}
                eventWindowLimited={eventWindowLimited}
              />
              <div
                className="pointer-events-none absolute inset-x-0 bottom-0 px-3 pb-4 pt-10 sm:px-6"
                data-testid="agent-composer-shell"
                data-placement="bottom"
              >
                <div className="pointer-events-auto">
                  <ComposerApprovalPopover events={state.events} />
                  {composer}
                </div>
              </div>
            </>
          ) : (
            <div className="flex min-h-0 flex-1 items-center justify-center px-4">
              <div className="w-full max-w-3xl -translate-y-10">
                <h1 className="mb-7 text-center text-2xl font-semibold tracking-normal text-foreground sm:text-3xl">
                  {t("welcomeTitle")}
                </h1>
                <div data-testid="agent-composer-shell" data-placement="center">
                  {composer}
                </div>
              </div>
            </div>
          )}

          {state.error ? (
            <div className="absolute inset-x-4 bottom-24 mx-auto max-w-3xl rounded-2xl border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive shadow-sm sm:bottom-28">
              {state.error}
            </div>
          ) : null}

          {environmentOpen && !desktopSidecarVisible ? (
            <div
              className="pointer-events-auto absolute right-3 top-3 z-20 w-[min(440px,calc(100%-1.5rem))] sm:right-5 sm:top-5"
              data-testid="agent-environment-floating-panel"
            >
              <AgentEnvironmentCard
                projectId={projectId}
                session={state.session}
                events={state.events}
                artifacts={transcriptArtifacts}
              />
            </div>
          ) : null}
        </main>

        <div
          className={cn(
            "hidden shrink-0 overflow-hidden transition-[width,opacity,transform] duration-300 ease-out lg:flex",
            desktopSidecarVisible
              ? cn(
                  "translate-x-0 opacity-100",
                  activeSidecarTab === "files"
                    ? "w-[clamp(600px,50vw,860px)]"
                    : "w-[clamp(360px,32vw,500px)]",
                )
              : "w-0 translate-x-4 opacity-0",
          )}
          aria-hidden={!desktopSidecarVisible}
          data-testid="agent-sidecar-column"
        >
          <div className="flex h-full w-full shrink-0 items-stretch">
            {desktopSidecarVisible ? (
                <AgentTabbedPanel
                  projectId={projectId}
                  sessionId={state.session?.id}
                  events={state.events}
                  activeTab={activeSidecarTab}
                  onActiveTabChange={setActiveSidecarTab}
                  browserInput={browserInput}
                  browserSrc={browserSrc}
                  onBrowserInputChange={setBrowserInput}
                  onBrowserSrcChange={setBrowserSrc}
                  onClose={closeSidecar}
                  onAddContext={addContextAttachment}
              />
            ) : null}
          </div>
        </div>

        {mobileSidecarVisible ? (
          <div
            className="fixed inset-0 z-50 bg-background/80 p-3 backdrop-blur-sm lg:hidden"
            data-testid="agent-mobile-sidecar-overlay"
          >
            <AgentTabbedPanel
              projectId={projectId}
              sessionId={state.session?.id}
              events={state.events}
              activeTab={activeSidecarTab}
              onActiveTabChange={setActiveSidecarTab}
              browserInput={browserInput}
              browserSrc={browserSrc}
              onBrowserInputChange={setBrowserInput}
              onBrowserSrcChange={setBrowserSrc}
              onClose={closeSidecar}
              onAddContext={addContextAttachment}
              variant="mobile"
              className="flex h-full w-full flex-col rounded-xl border border-border/70 shadow-[0_18px_48px_rgba(60,64,67,0.12)]"
            />
          </div>
        ) : null}
      </div>
    )
  },
)

function createOptimisticTurn({
  text,
  inputParts,
  sessionId,
  projectId,
}: {
  text: string
  inputParts: AgentRuntimeInputPart[]
  sessionId: string
  projectId?: string | null
}): AgentRuntimeTurn {
  const now = new Date().toISOString()
  return {
    id: `optimistic-${now}`,
    session_id: sessionId,
    project_id: projectId ?? null,
    workspace_id: "pending",
    user_id: "pending",
    input_text: text,
    input_parts: inputParts,
    status: "queued",
    model_selection: null,
    model_profile_snapshot: null,
    final_text: null,
    token_usage: null,
    termination_reason: null,
    loop_state: { state: "queued", optimistic: true },
    iteration_count: 0,
    budget_snapshot: null,
    interrupt_requested_at: null,
    error_code: null,
    error_message: null,
    created_at: now,
    updated_at: now,
    started_at: null,
    completed_at: null,
  }
}

function getSessionRemoteConnectionId(metadata: Record<string, unknown> | null | undefined): string {
  const value = metadata?.remote_connection_id
  return typeof value === "string" ? value : ""
}
