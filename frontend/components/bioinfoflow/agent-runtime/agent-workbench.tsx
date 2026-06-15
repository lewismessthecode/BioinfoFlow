"use client"

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react"
import { PanelRightClose, PanelRightOpen } from "lucide-react"
import { useTranslations } from "next-intl"

import { AgentComposer } from "./agent-composer"
import { AgentTabbedPanel } from "./agent-tabbed-panel"
import { AgentTranscript } from "./agent-transcript"
import { hasPendingRuntimeAction, pendingDecisionKey } from "./pending-actions"
import { Button } from "@/components/ui/button"
import { useOptionalWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { useAgentRuntime } from "@/hooks/use-agent-runtime"
import { useLlmSettings } from "@/hooks/use-llm-settings"
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
    const [hasSubmittedDraft, setHasSubmittedDraft] = useState(false)
    const [sidecarOpen, setSidecarOpen] = useState(false)
    // The pending-approval key the user last dismissed. Storing the key (rather
    // than a boolean) means a *new* approval — which has a different key — is
    // never suppressed by an earlier dismissal, without needing an effect.
    const [dismissedPendingKey, setDismissedPendingKey] = useState<string | null>(null)
    const workspaceShell = useOptionalWorkspaceShell()
    const setNavbarActions = workspaceShell?.setNavbarActions
    const { models, selectedModel, isLoading: modelsLoading, setSelectedModel } =
      useLlmSettings()
    const {
      state,
      mode,
      setMode,
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
    const pendingDecision = hasPendingRuntimeAction(state.events)
    const pendingKey = pendingDecisionKey(state.events)
    // Auto-open only for a pending approval (genuinely actionable). Streaming
    // is already visible inline in the transcript, so it no longer forces the
    // panel open. A dismissal only suppresses the exact approval set it was
    // made against, so a newly-arrived approval still surfaces.
    const sidecarVisible =
      sidecarOpen || (pendingDecision && pendingKey !== dismissedPendingKey)
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
          setHasSubmittedDraft(false)
          setSidecarOpen(false)
          setDismissedPendingKey(null)
        },
      }),
      [interrupt, setActiveSessionId],
    )

    const submit = () => {
      const text = input.trim()
      if (!text) return
      setHasSubmittedDraft(true)
      void send(text, { modelSelection: selectedModel })
      setInput("")
    }

    const closeSidecar = useCallback(() => {
      setSidecarOpen(false)
      setDismissedPendingKey(pendingKey)
    }, [pendingKey])

    const toggleSidecar = useCallback(() => {
      if (sidecarVisible) {
        closeSidecar()
        return
      }
      setSidecarOpen(true)
      setDismissedPendingKey(null)
    }, [closeSidecar, sidecarVisible])

    useEffect(() => {
      if (!setNavbarActions) return

      setNavbarActions(
        <Button
          type="button"
          variant="ghost"
          size="icon"
          className="h-8 w-8 rounded-full border border-transparent text-foreground/78 transition-colors hover:bg-accent hover:text-foreground"
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
        onModeChange={(next) => void setMode?.(next)}
        models={models}
        selectedModel={selectedModel}
        modelsLoading={modelsLoading}
        onSelectModel={(model) => void setSelectedModel(model)}
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
              <AgentTranscript timeline={state.timeline} />
              <div
                className="pointer-events-none absolute inset-x-0 bottom-0 px-3 pb-4 pt-10 sm:px-6"
                data-testid="agent-composer-shell"
                data-placement="bottom"
              >
                <div className="pointer-events-auto">{composer}</div>
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
              ? "w-[404px] translate-x-0 opacity-100"
              : "w-0 translate-x-4 opacity-0",
          )}
          aria-hidden={!sidecarVisible}
          data-testid="agent-sidecar-column"
        >
          <div className="flex h-full w-[404px] shrink-0 items-center py-4 pr-4">
            {sidecarVisible ? (
              <AgentTabbedPanel
                projectId={projectId}
                sessionId={state.session?.id}
                events={state.events}
                onClose={closeSidecar}
                onDecision={decideAction}
              />
            ) : null}
          </div>
        </div>
      </div>
    )
  },
)
