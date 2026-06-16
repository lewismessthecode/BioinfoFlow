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
import { PanelRightClose, PanelRightOpen } from "lucide-react"
import { useTranslations } from "next-intl"

import { AgentComposer } from "./agent-composer"
import { AgentTabbedPanel } from "./agent-tabbed-panel"
import { AgentTranscript } from "./agent-transcript"
import { ComposerApprovalPopover } from "./composer-approval-popover"
import { Button } from "@/components/ui/button"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import {
  listAgentRuntimeSessionArtifacts,
  type AgentRuntimeArtifact,
  type AgentRuntimeFileRefPart,
  type AgentRuntimeInputPart,
} from "@/lib/agent-runtime"
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
    const [input, setInput] = useState("")
    const [contextAttachments, setContextAttachments] = useState<AgentRuntimeFileRefPart[]>([])
    const [hasSubmittedDraft, setHasSubmittedDraft] = useState(false)
    const [sidecarOpen, setSidecarOpen] = useState(false)
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

    const disabled = !workspaceEnabled
    const hasTurns = state.turns.length > 0
    const hasConversation = hasTurns || hasSubmittedDraft
    const isRunning = state.status === "running"
    const artifactEventCount = useMemo(
      () => state.events.filter((event) => event.type === "artifact.created").length,
      [state.events],
    )
    const transcriptArtifacts =
      artifactState && artifactState.sessionId === state.session?.id
        ? artifactState.artifacts
        : []
    // The side panel is now secondary detail. Approvals surface inline and above
    // the composer, so pending decisions no longer force the drawer open.
    const sidecarVisible = sidecarOpen
    const sidecarLabel = sidecarVisible
      ? t("sidecar.collapse")
      : t("sidecar.expand")

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
          setHasSubmittedDraft(false)
          setSidecarOpen(false)
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

    const submit = () => {
      const text = input.trim()
      if (!text) return
      setHasSubmittedDraft(true)
      const inputParts: AgentRuntimeInputPart[] = [
        { type: "text", text },
        ...contextAttachments,
      ]
      void send(text, { modelSelection: selectedModel, inputParts })
      setInput("")
      setContextAttachments([])
    }

    const closeSidecar = useCallback(() => {
      setSidecarOpen(false)
    }, [])

    const toggleSidecar = useCallback(() => {
      if (sidecarVisible) {
        closeSidecar()
        return
      }
      setSidecarOpen(true)
    }, [closeSidecar, sidecarVisible])

    useEffect(() => {
      if (!setNavbarActions) return

      setNavbarActions(
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-lg border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"
          onClick={toggleSidecar}
          aria-label={sidecarLabel}
        >
          {sidecarVisible ? (
            <PanelRightClose className="h-4 w-4" />
          ) : (
            <PanelRightOpen className="h-4 w-4" />
          )}
        </Button>,
      )

      return () => setNavbarActions(null)
    }, [setNavbarActions, sidecarLabel, sidecarVisible, toggleSidecar])

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
              <AgentTranscript
                timeline={state.timeline}
                artifacts={transcriptArtifacts}
                events={state.events}
                onDecision={decideAction}
              />
              <div
                className="pointer-events-none absolute inset-x-0 bottom-0 px-3 pb-4 pt-10 sm:px-6"
                data-testid="agent-composer-shell"
                data-placement="bottom"
              >
                <div className="pointer-events-auto">
                  <ComposerApprovalPopover events={state.events} onDecision={decideAction} />
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
        </main>

        <div
          className={cn(
            "hidden shrink-0 overflow-hidden transition-[width,opacity,transform] duration-300 ease-out lg:flex",
            sidecarVisible
              ? "w-[420px] translate-x-0 opacity-100"
              : "w-0 translate-x-4 opacity-0",
          )}
          aria-hidden={!sidecarVisible}
          data-testid="agent-sidecar-column"
        >
          <div className="flex h-full w-[420px] shrink-0 items-stretch">
            {sidecarVisible ? (
              <AgentTabbedPanel
                projectId={projectId}
                sessionId={state.session?.id}
                events={state.events}
                onClose={closeSidecar}
                onDecision={decideAction}
                onAddContext={addContextAttachment}
              />
            ) : null}
          </div>
        </div>
      </div>
    )
  },
)
