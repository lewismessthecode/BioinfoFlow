"use client"

import type React from "react"
import { forwardRef, useImperativeHandle, useMemo, useRef, useState } from "react"
import {
  Check,
  FlaskConical,
  MessageCircle,
  ShieldAlert,
  ShieldCheck,
  Upload,
  Zap,
} from "@/lib/icons"
import { useTranslations } from "next-intl"
import { toast } from "sonner"

import { WelcomeCard } from "@/components/bioinfoflow/welcome-card"
import { AgentCoreTurnBlock } from "@/components/bioinfoflow/agent-core/agent-core-turn-block"
import { ChatInput } from "@/components/bioinfoflow/chat/chat-input"
import { ModelSelector } from "@/components/bioinfoflow/chat/model-selector"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { cn } from "@/lib/utils"
import { useAgentCore } from "@/hooks/use-agent-core"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { clearStoredAgentSessionId } from "@/lib/agent-core/session-storage"
import type {
  AgentCoreEvent,
  AgentCoreMemory,
  AgentModelSelection,
  AgentPermissionMode,
} from "@/lib/agent-core"

const SUGGESTION_ICONS = [Upload, FlaskConical, MessageCircle] as const

type AgentCoreChatProps = {
  projectId?: string
  activeSessionId?: string
  onActiveSessionIdChange?: (sessionId: string) => void
  onQuickCreateProject?: (data: { name: string; description: string }) => Promise<void>
  onOpenCreateProjectDialog?: () => void
  workspaceEnabled?: boolean
  className?: string
}

export type AgentCoreChatHandle = {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

export const AgentCoreChat = forwardRef<AgentCoreChatHandle, AgentCoreChatProps>(
  function AgentCoreChat({
    projectId,
    activeSessionId,
    onActiveSessionIdChange,
    onQuickCreateProject,
    onOpenCreateProjectDialog,
    workspaceEnabled = true,
    className,
  }, ref) {
    const t = useTranslations("agentCore")
    const textareaRef = useRef<HTMLTextAreaElement>(null)
    const [input, setInput] = useState("")
    const {
      models,
      selectedModel,
      isLoading: settingsLoading,
      setSelectedModel,
    } = useLlmSettings()
    const {
      turns,
      events,
      artifactsByTurn,
      proposedMemories,
      isLoading,
      status,
      error,
      sendTurn,
      setActiveSessionId,
      activeModelSelection,
      activePermissionMode,
      updateSessionSettings,
      approveAction,
      rejectAction,
      acceptMemory,
      rejectMemory,
    } = useAgentCore(projectId, {
      activeSessionId,
      onActiveSessionIdChange,
    })

    useImperativeHandle(
      ref,
      () => ({
        focusInput: () => textareaRef.current?.focus(),
        stop: () => undefined,
        newConversation: () => {
          if (projectId) clearStoredAgentSessionId(projectId)
          setActiveSessionId(null)
          setInput("")
        },
      }),
      [projectId, setActiveSessionId],
    )

    const eventsByTurn = useMemo(() => groupEventsByTurn(events), [events])
    const disabled = !projectId || !workspaceEnabled || status === "running"
    const composerControls = (
      <AgentComposerControls
        disabled={disabled}
        models={models}
        selectedModel={selectedModel}
        isModelLoading={settingsLoading}
        permissionMode={activePermissionMode}
        onSelectedModelChange={(modelSelection) => {
          void setSelectedModel(modelSelection)
          void updateSessionSettings({
            modelSelection,
          })
        }}
        onPermissionModeChange={(permissionMode) => {
          return updateSessionSettings({ permissionMode })
        }}
      />
    )

    const handleSend = () => {
      const text = input.trim()
      if (!text) return
      void sendTurn(text, {
        modelSelection: selectedModel ?? activeModelSelection ?? null,
      })
      setInput("")
    }

    if (!projectId) {
      return (
        <div className={cn("flex h-full items-center justify-center bg-background p-5", className)}>
          <div className="w-full max-w-4xl">
            <WelcomeCard
              onQuickCreate={onQuickCreateProject ?? (async () => undefined)}
              onOpenCreateDialog={onOpenCreateProjectDialog ?? (() => undefined)}
            />
          </div>
        </div>
      )
    }

    const isDraft = !isLoading && turns.length === 0

    return (
      <div
        className={cn(
          "flex h-full flex-col bg-background",
          isDraft && "agent-halo-surface",
          className,
        )}
      >
        <div className="min-h-0 flex-1 overflow-y-auto px-4 py-5 sm:px-6">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">{t("loading")}</div>
          ) : turns.length === 0 ? (
            <DraftWelcome
              disabled={disabled}
              input={input}
              modelSelector={composerControls}
              onInputChange={setInput}
              onSend={handleSend}
              onStop={() => undefined}
              status={status}
              textareaRef={textareaRef}
            />
          ) : (
            <div className="mx-auto flex w-full max-w-5xl flex-col gap-8 py-6">
              {turns.map((turn) => (
                <AgentCoreTurnBlock
                  key={turn.id}
                  turn={turn}
                  events={eventsByTurn.get(turn.id) ?? []}
                  artifacts={artifactsByTurn.get(turn.id) ?? []}
                  memories={filterMemoriesForTurn(proposedMemories, turn.id)}
                  onApproveAction={approveAction}
                  onRejectAction={rejectAction}
                  onAcceptMemory={acceptMemory}
                  onRejectMemory={rejectMemory}
                />
              ))}
            </div>
          )}
          {error ? (
            <div className="mx-auto mt-4 max-w-4xl rounded-2xl border border-destructive/30 bg-destructive/5 px-4 py-3 text-sm text-destructive">
              {error.message}
            </div>
          ) : null}
        </div>

        {turns.length > 0 ? (
          <div className="px-4 pb-4 pt-2">
            <ChatInput
              input={input}
              onInputChange={setInput}
              onSend={handleSend}
              onStop={() => undefined}
              isStreaming={status === "running"}
              disabled={disabled}
              textareaRef={textareaRef}
              modelSelector={composerControls}
              variant="thread"
            />
          </div>
        ) : null}
      </div>
    )
  },
)

function DraftWelcome({
  disabled,
  input,
  modelSelector,
  onInputChange,
  onSend,
  onStop,
  status,
  textareaRef,
}: {
  disabled: boolean
  input: string
  modelSelector: React.ReactNode
  onInputChange: (value: string) => void
  onSend: () => void
  onStop: () => void
  status: "idle" | "running" | "error"
  textareaRef: React.RefObject<HTMLTextAreaElement | null>
}) {
  const tAgent = useTranslations("agent")
  const tChat = useTranslations("chat")
  const greeting = useTimeGreeting()
  const suggestions = [
    { key: "upload" as const, descKey: "uploadDescription" as const },
    { key: "tryDemo" as const, descKey: "tryDemoDescription" as const },
    { key: "askQuestion" as const, descKey: "askQuestionDescription" as const },
  ]

  return (
    <div className="agent-center-stage mx-auto flex min-h-full w-full flex-col items-center justify-center px-2 pb-[11vh] pt-8 text-center">
      <h2 className="mb-7 text-center text-[1.85rem] font-normal leading-tight tracking-normal text-foreground animate-in fade-in duration-500 md:text-[2.35rem] lg:text-[2.5rem]">
        {greeting}
      </h2>
      <div className="w-full">
        <ChatInput
          input={input}
          onInputChange={onInputChange}
          onSend={onSend}
          onStop={onStop}
          isStreaming={status === "running"}
          disabled={disabled}
          textareaRef={textareaRef}
          modelSelector={modelSelector}
          variant="home"
        />
      </div>
      <div className="mt-6 flex max-w-2xl flex-wrap justify-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-500 delay-150">
        {suggestions.map(({ key, descKey }, index) => {
          const Icon = SUGGESTION_ICONS[index]
          return (
            <button
              key={key}
              type="button"
              className="group flex items-center gap-2 rounded-full border border-border/80 bg-white/65 px-3 py-2 text-[13px] text-muted-foreground shadow-[0_1px_2px_rgba(60,64,67,0.04)] transition-all duration-200 hover:border-foreground/20 hover:bg-white hover:text-foreground dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"
              onClick={() => onInputChange(tChat(`quickStart.${descKey}`))}
            >
              <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70 transition-colors group-hover:text-primary" />
              <span>{tChat(`quickStart.${key}`)}</span>
            </button>
          )
        })}
      </div>
      <p className="mt-8 text-center text-xs text-muted-foreground/65">
        {tAgent("disclaimer")}
      </p>
    </div>
  )
}

function useTimeGreeting() {
  const t = useTranslations("greeting")
  return useMemo(() => {
    const hour = new Date().getHours()
    if (hour >= 5 && hour < 12) return t("morning")
    if (hour >= 12 && hour < 17) return t("afternoon")
    if (hour >= 17 && hour < 22) return t("evening")
    return t("lateNight")
  }, [t])
}

function AgentComposerControls({
  disabled,
  models,
  selectedModel,
  permissionMode,
  isModelLoading,
  onSelectedModelChange,
  onPermissionModeChange,
}: {
  disabled: boolean
  models: ReturnType<typeof useLlmSettings>["models"]
  selectedModel: AgentModelSelection | null
  permissionMode: AgentPermissionMode
  isModelLoading: boolean
  onSelectedModelChange: (model: AgentModelSelection | null) => void
  onPermissionModeChange: (mode: AgentPermissionMode) => void | Promise<unknown>
}) {
  return (
    <div className="flex items-center gap-1">
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        onSelectModel={onSelectedModelChange}
        disabled={disabled || isModelLoading}
        allowAuto
      />
      <AgentPermissionModeSelector
        disabled={disabled}
        value={permissionMode}
        onChange={onPermissionModeChange}
      />
    </div>
  )
}

function AgentPermissionModeSelector({
  value,
  onChange,
  disabled,
}: {
  value: AgentPermissionMode
  onChange: (mode: AgentPermissionMode) => void | Promise<void>
  disabled?: boolean
}) {
  const t = useTranslations("executionMode")
  const active = value

  const handleSelect = async (next: AgentPermissionMode) => {
    if (next === active) return
    try {
      await onChange(next)
    } catch {
      toast.error(t("changeFailed"))
    }
  }

  const trigger = useMemo(() => {
    if (active === "bypass") {
      return {
        icon: <Zap className="h-3.5 w-3.5" aria-hidden />,
        label: t("bypassShort"),
        cls: "text-amber-600 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300",
      }
    }
    if (active === "ask_each_action") {
      return {
        icon: <ShieldAlert className="h-3.5 w-3.5" aria-hidden />,
        label: t("approveAllShort"),
        cls: "text-foreground",
      }
    }
    return {
      icon: <ShieldCheck className="h-3.5 w-3.5" aria-hidden />,
      label: t("askShort"),
      cls: "text-muted-foreground hover:text-foreground",
    }
  }, [active, t])

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className={cn(
            "h-9 gap-1.5 rounded-full border border-border/55 bg-background/72 px-3 text-xs font-medium shadow-[0_8px_20px_rgba(15,23,42,0.06)] backdrop-blur transition-colors hover:bg-background",
            trigger.cls,
          )}
          disabled={disabled}
          aria-label={t("triggerAriaLabel")}
          title={t("menuLabel")}
        >
          {trigger.icon}
          <span className="hidden sm:inline">{trigger.label}</span>
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        className="w-80 rounded-[22px] border-border/80 bg-popover p-1.5 shadow-[0_18px_50px_rgba(15,23,42,0.16)]"
      >
        <DropdownMenuLabel className="px-4 py-3 text-[15px] font-semibold text-foreground">
          {t("menuLabel")}
        </DropdownMenuLabel>
        <DropdownMenuSeparator className="mx-2 my-0" />
        <PermissionModeItem
          icon={<ShieldCheck className="h-4 w-4" />}
          title={t("askTitle")}
          description={t("askDescription")}
          active={active === "guarded_auto"}
          onSelect={() => void handleSelect("guarded_auto")}
        />
        <PermissionModeItem
          icon={<ShieldAlert className="h-4 w-4" />}
          title={t("approveAllTitle")}
          description={t("approveAllDescription")}
          active={active === "ask_each_action"}
          onSelect={() => void handleSelect("ask_each_action")}
        />
        <PermissionModeItem
          icon={<Zap className="h-4 w-4 text-amber-500" />}
          title={t("bypassTitle")}
          description={t("bypassDescription")}
          active={active === "bypass"}
          onSelect={() => void handleSelect("bypass")}
        />
      </DropdownMenuContent>
    </DropdownMenu>
  )
}

function PermissionModeItem({
  icon,
  title,
  description,
  active,
  onSelect,
}: {
  icon: React.ReactNode
  title: string
  description: string
  active: boolean
  onSelect: () => void
}) {
  return (
    <DropdownMenuItem
      onClick={onSelect}
      className="my-1 cursor-pointer items-start gap-3 rounded-2xl px-3 py-3 focus:bg-muted/70"
    >
      <div className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-muted/70 text-muted-foreground">
        {icon}
      </div>
      <div className="min-w-0 flex-1 space-y-1">
        <div className="flex items-center justify-between gap-3">
          <span className="text-sm font-medium leading-5 text-foreground">
            {title}
          </span>
          {active ? (
            <Check className="h-3.5 w-3.5 shrink-0 text-emerald-500" aria-hidden />
          ) : null}
        </div>
        <p className="whitespace-normal text-xs leading-5 text-muted-foreground">
          {description}
        </p>
      </div>
    </DropdownMenuItem>
  )
}

function groupEventsByTurn(events: AgentCoreEvent[]) {
  const grouped = new Map<string, AgentCoreEvent[]>()
  for (const event of events) {
    const list = grouped.get(event.turn_id) ?? []
    list.push(event)
    grouped.set(event.turn_id, list)
  }
  return grouped
}

function filterMemoriesForTurn(
  memories: AgentCoreMemory[],
  turnId: string,
) {
  return memories.filter((memory) => {
    const memoryTurnId = readString(memory.source?.turn_id)
    return !memoryTurnId || memoryTurnId === turnId
  })
}

function readString(value: unknown) {
  return typeof value === "string" && value.length > 0 ? value : null
}
