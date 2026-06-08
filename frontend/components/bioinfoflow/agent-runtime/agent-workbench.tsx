"use client"

import {
  forwardRef,
  useImperativeHandle,
  useMemo,
  useRef,
  useState,
} from "react"
import { Send, Square, Workflow } from "lucide-react"
import { useTranslations } from "next-intl"

import { ActionApprovalPanel } from "./action-approval-panel"
import { ArtifactsPanel } from "./artifacts-panel"
import { MemoryPanel } from "./memory-panel"
import { ToolActivityPanel } from "./tool-activity-panel"
import { TranscriptPane } from "./transcript-pane"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Button } from "@/components/ui/button"
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
    const { models, selectedModel, isLoading: modelsLoading, setSelectedModel } =
      useLlmSettings()
    const {
      state,
      session,
      setActiveSessionId,
      send,
      interrupt,
      decideAction,
    } = useAgentRuntime(projectId, {
      activeSessionId,
      onActiveSessionIdChange,
    })
    const disabled = !workspaceEnabled
    const isRunning = state.status === "running"
    const eventCount = state.events.length
    const lastSeq = state.events.at(-1)?.seq ?? 0

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
        },
      }),
      [interrupt, setActiveSessionId],
    )

    const runtimeLabel = useMemo(() => {
      if (!session) return t("draftSession")
      return session.project_id ? t("projectSession") : t("workspaceSession")
    }, [session, t])

    const submit = () => {
      const text = input.trim()
      if (!text) return
      void send(text, { modelSelection: selectedModel })
      setInput("")
    }

    return (
      <div className={cn("flex h-full min-w-0 bg-background", className)}>
        <main className="flex min-w-0 flex-1 flex-col">
          <header className="flex min-h-14 items-center justify-between border-b border-border px-4 sm:px-6">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-sm font-semibold text-foreground">
                <Workflow className="h-4 w-4 text-primary" />
                {t("title")}
              </div>
              <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
                <span>{runtimeLabel}</span>
                <span className="font-mono">events:{eventCount}</span>
                <span className="font-mono">seq:{lastSeq}</span>
              </div>
            </div>
            <ModelSelector
              models={models}
              selectedModel={selectedModel}
              onSelectModel={(model) => void setSelectedModel(model)}
              disabled={modelsLoading || disabled}
              allowAuto
            />
          </header>

          <TranscriptPane turns={state.turns} />

          {state.error ? (
            <div className="mx-4 mb-2 border border-destructive/30 bg-destructive/5 px-3 py-2 text-sm text-destructive sm:mx-6">
              {state.error}
            </div>
          ) : null}

          <footer className="border-t border-border p-3 sm:p-4">
            <div className="mx-auto flex max-w-4xl items-end gap-2 border border-border bg-background p-2 shadow-sm">
              <textarea
                ref={textareaRef}
                value={input}
                onChange={(event) => setInput(event.target.value)}
                onKeyDown={(event) => {
                  if ((event.metaKey || event.ctrlKey) && event.key === "Enter") {
                    event.preventDefault()
                    submit()
                  }
                }}
                placeholder={t("composerPlaceholder")}
                className="max-h-40 min-h-12 flex-1 resize-none bg-transparent px-2 py-2 text-sm leading-6 outline-none placeholder:text-muted-foreground"
                disabled={disabled}
              />
              {isRunning ? (
                <Button type="button" variant="outline" size="icon" onClick={() => void interrupt()}>
                  <Square className="h-4 w-4" />
                </Button>
              ) : (
                <Button type="button" size="icon" onClick={submit} disabled={disabled || !input.trim()}>
                  <Send className="h-4 w-4" />
                </Button>
              )}
            </div>
          </footer>
        </main>

        <aside className="hidden w-[330px] shrink-0 border-l border-border bg-muted/20 lg:block">
          <ActionApprovalPanel events={state.events} onDecision={decideAction} />
          <ToolActivityPanel events={state.events} />
          <ArtifactsPanel events={state.events} />
          <MemoryPanel events={state.events} />
        </aside>
      </div>
    )
  },
)
