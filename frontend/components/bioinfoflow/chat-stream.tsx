"use client"

import { useState, useMemo, useCallback, useRef, useImperativeHandle, forwardRef } from "react"
import { Upload, FlaskConical, MessageCircle, Download } from "lucide-react"
import { useTranslations } from "next-intl"

import { cn } from "@/lib/utils"
import { useAgentChat } from "@/hooks/use-agent-chat"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import { WelcomeCard } from "@/components/bioinfoflow/welcome-card"
import { ChatInput } from "./chat/chat-input"
import { MessageList } from "./chat/message-list"
import { ModelSelector } from "./chat/model-selector"
import { ExecutionModeSelector } from "./chat/execution-mode-selector"
import { BypassBanner } from "./chat/bypass-banner"
import { ScrollToBottom } from "./chat/scroll-to-bottom"
import { SetupBanner } from "./chat/setup-banner"
import { downloadConversation } from "@/lib/conversation-export"
import { Button } from "@/components/ui/button"
import { apiRequest } from "@/lib/api"
import { toast } from "sonner"

// ── Helpers ────────────────────────────────────────────────────────

function useTimeGreeting() {
  const t = useTranslations("greeting")
  return useMemo(() => {
    const h = new Date().getHours()
    if (h >= 5 && h < 12) return t("morning")
    if (h >= 12 && h < 17) return t("afternoon")
    if (h >= 17 && h < 22) return t("evening")
    return t("lateNight")
  }, [t])
}

const SUGGESTION_ICONS = [Upload, FlaskConical, MessageCircle] as const

// ── Component ──────────────────────────────────────────────────────

interface ChatStreamProps {
  projectId?: string
  workspaceEnabled?: boolean
  className?: string
}

export interface ChatStreamHandle {
  focusInput: () => void
  stop: () => void
  newConversation: () => void
}

export const ChatStream = forwardRef<ChatStreamHandle, ChatStreamProps>(function ChatStream({
  projectId,
  workspaceEnabled = true,
  className,
}, ref) {
  const [input, setInput] = useState("")
  const tChat = useTranslations("chat")
  const tAgent = useTranslations("agent")
  const workspaceShell = useWorkspaceShell()
  const chatInputRef = useRef<HTMLTextAreaElement>(null)

  const {
    messages,
    isLoading,
    status,
    sendMessage,
    stop,
    regenerate,
    editAndResend,
    resolveApproval,
    currentActivity,
    tokenUsage,
    executionPolicy,
    setExecutionPolicy,
    newConversation,
    messagesEndRef,
    scrollContainerRef,
    scrollFabProps,
  } = useAgentChat(projectId)

  const { models, selectedModel, setSelectedModel, hasConfiguredProvider } =
    useLlmSettings()

  useImperativeHandle(ref, () => ({
    focusInput: () => chatInputRef.current?.focus(),
    stop,
    newConversation,
  }), [stop, newConversation])

  const greeting = useTimeGreeting()
  const isEmpty = !isLoading && messages.length === 0 && !!projectId
  const showWorkspaceOnboarding =
    !projectId && !workspaceShell.isLoading && !workspaceShell.hasProjects
  const showInboxWorkspaceNotice = Boolean(projectId) && !workspaceEnabled

  const handleSend = () => {
    if (!input.trim()) return
    sendMessage(input.trim(), selectedModel || undefined)
    setInput("")
  }

  const handleSuggestionClick = (text: string) => {
    sendMessage(text, selectedModel || undefined)
  }

  const handleFileDrop = useCallback(async (files: File[]) => {
    if (!projectId || !workspaceEnabled) return
    const results = await Promise.allSettled(
      files.map(async (file) => {
        const formData = new FormData()
        formData.append("file", file)
        formData.append("project_id", projectId)
        await apiRequest("/files/upload", { method: "POST", body: formData })
        return file.name
      }),
    )
    const uploaded: string[] = []
    for (const result of results) {
      if (result.status === "fulfilled") {
        uploaded.push(result.value)
        toast.success(`Uploaded ${result.value}`)
      } else {
        toast.error("Failed to upload a file")
      }
    }
    if (uploaded.length > 0) {
      const attachments = uploaded.map((name) => `[Uploaded: ${name}]`).join("\n")
      setInput((prev) => `${prev}${prev ? "\n" : ""}${attachments}`)
    }
  }, [projectId, workspaceEnabled])

  const suggestions = [
    { key: "upload" as const, descKey: "uploadDescription" as const },
    { key: "tryDemo" as const, descKey: "tryDemoDescription" as const },
    { key: "askQuestion" as const, descKey: "askQuestionDescription" as const },
  ]

  const modelSelector = (
    <>
      <ModelSelector
        models={models}
        selectedModel={selectedModel}
        onSelectModel={setSelectedModel}
        disabled={status === "streaming"}
      />
      <ExecutionModeSelector
        value={executionPolicy}
        onChange={setExecutionPolicy}
        disabled={status === "streaming"}
      />
    </>
  )

  const bypassActive = executionPolicy === "bypass"

  const inboxWorkspaceNotice = showInboxWorkspaceNotice ? (
    <div className="mb-4 rounded-2xl border border-dashed border-border/70 bg-muted/25 px-4 py-3 text-left">
      <p className="text-sm font-medium text-foreground">
        {tChat("inboxWorkspaceTitle")}
      </p>
      <p className="mt-1 text-sm leading-6 text-muted-foreground">
        {tChat("inboxWorkspaceDescription")}
      </p>
    </div>
  ) : null

  if (showWorkspaceOnboarding) {
    return (
      <div className={cn("flex h-full flex-col bg-background", className)}>
        <div className="flex flex-1 items-center justify-center px-4 py-8">
          <div className="w-full max-w-5xl">
            <WelcomeCard
              onQuickCreate={workspaceShell.handleQuickCreateProject}
              onOpenCreateDialog={workspaceShell.openCreateProjectDialog}
            />
          </div>
        </div>
      </div>
    )
  }

  if (!projectId) {
    return (
      <div className={cn("flex h-full flex-col bg-background", className)}>
        <div className="flex flex-1 items-center justify-center px-4 py-8">
          <div className="w-full max-w-3xl rounded-[28px] border border-border/70 bg-muted/20 p-8 text-center shadow-[0_20px_50px_-40px_rgba(15,23,42,0.45)]">
            <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 text-primary">
              <MessageCircle className="h-6 w-6" />
            </div>
            <h2 className="mt-5 text-2xl font-semibold tracking-tight text-foreground">
              {tChat("selectProject")}
            </h2>
            <p className="mx-auto mt-2 max-w-lg text-sm leading-6 text-muted-foreground">
              {tChat("selectProjectDescription")}
            </p>
          </div>
        </div>
      </div>
    )
  }

  // ── Welcome layout (empty conversation) ──────────────────────────

  if (isEmpty) {
    return (
      <div className={cn("agent-halo-surface flex h-full flex-col", className)}>
        <div className="agent-center-stage flex flex-1 flex-col items-center justify-center px-4 pb-[11vh] pt-8">
          {/* Greeting */}
          <h2 className="mb-7 text-center text-[1.85rem] font-normal leading-tight tracking-normal text-foreground animate-in fade-in duration-500 md:text-[2.35rem] lg:text-[2.5rem]">
            {greeting}
          </h2>

          {/* Centered input */}
          {!hasConfiguredProvider && <SetupBanner className="mb-4 max-w-2xl w-full" />}
          {inboxWorkspaceNotice}
          <ChatInput
            input={input}
            onInputChange={setInput}
            onSend={handleSend}
            onStop={stop}
            onFileDrop={workspaceEnabled ? handleFileDrop : undefined}
            isStreaming={status === "streaming"}
            disabled={!projectId}
            modelSelector={modelSelector}
            textareaRef={chatInputRef}
            centered
            variant="home"
          />

          {/* Quick-start suggestions */}
          <div className="mt-6 flex max-w-2xl flex-wrap justify-center gap-2 animate-in fade-in slide-in-from-bottom-2 duration-500 delay-150">
            {suggestions.map(({ key, descKey }, i) => {
              const Icon = SUGGESTION_ICONS[i]
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => handleSuggestionClick(tChat(`quickStart.${descKey}`))}
                  className="group flex items-center gap-2 rounded-full border border-border/80 bg-white/65 px-3 py-2 text-[13px] text-muted-foreground shadow-[0_1px_2px_rgba(60,64,67,0.04)] transition-all duration-200 hover:border-foreground/20 hover:bg-white hover:text-foreground dark:bg-white/[0.04] dark:hover:bg-white/[0.08]"
                >
                  <Icon className="h-3.5 w-3.5 shrink-0 text-muted-foreground/70 group-hover:text-primary transition-colors" />
                  <span>{tChat(`quickStart.${key}`)}</span>
                </button>
              )
            })}
          </div>

          {/* Disclaimer */}
          <p className="mt-8 text-center text-xs text-muted-foreground/65">
            {tAgent("disclaimer")}
          </p>
        </div>
      </div>
    )
  }

  // ── Conversation layout (messages present or no project) ─────────

  return (
    <div className={cn("flex h-full flex-col bg-background", className)}>
      <BypassBanner
        visible={bypassActive}
        onDisable={() => {
          void setExecutionPolicy("auto")
        }}
      />
      {/* Agent activity status bar */}
      {currentActivity && (
        <div className="flex items-center gap-2 px-4 py-1.5 border-b border-border/50 bg-muted/30">
          {status === "streaming" ? (
            <span className="relative flex h-2 w-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-primary/60" />
              <span className="relative inline-flex h-2 w-2 rounded-full bg-primary" />
            </span>
          ) : (
            <span className="inline-flex h-2 w-2 rounded-full bg-muted-foreground/40" />
          )}
          <span className="text-xs text-muted-foreground truncate">{currentActivity}</span>
        </div>
      )}
      <div
        ref={scrollContainerRef}
        className="relative flex-1 overflow-y-auto scroll-smooth"
      >
        {showInboxWorkspaceNotice ? (
          <div className="mx-auto w-full max-w-3xl px-4 pt-4">
            {inboxWorkspaceNotice}
          </div>
        ) : null}
        <MessageList
          messages={messages}
          status={status}
          isLoading={isLoading}
          projectId={projectId}
          messagesEndRef={messagesEndRef}
          onRegenerate={regenerate}
          onResolveApproval={resolveApproval}
          onEdit={editAndResend}
        />
      </div>

      <ScrollToBottom {...scrollFabProps} />

      <div className="border-t border-border/35 bg-background/88 p-4 pb-6 backdrop-blur-xl">
        {!hasConfiguredProvider && <SetupBanner className="mb-3" />}
        {!messages.length && inboxWorkspaceNotice}
        <ChatInput
          input={input}
          onInputChange={setInput}
          onSend={handleSend}
          onStop={stop}
          onFileDrop={workspaceEnabled ? handleFileDrop : undefined}
          isStreaming={status === "streaming"}
          disabled={!projectId}
          modelSelector={modelSelector}
          textareaRef={chatInputRef}
          variant="thread"
        />
        <div className="mt-2 flex items-center justify-center gap-2">
          <p className="text-xs text-muted-foreground">
            {tAgent("disclaimer")}
          </p>
          {messages.length > 0 && (
            <Button
              variant="ghost"
              size="sm"
              className="h-5 px-1.5 text-[10px] text-muted-foreground/60 hover:text-foreground"
              onClick={() => downloadConversation(messages, "markdown")}
            >
              <Download className="h-3 w-3 mr-0.5" />
              Export
            </Button>
          )}
          {tokenUsage && (
            <span className="text-[10px] text-muted-foreground/40 tabular-nums" title={`Input: ${tokenUsage.input.toLocaleString()} | Output: ${tokenUsage.output.toLocaleString()} | Context: ${tokenUsage.context.toLocaleString()}`}>
              {((tokenUsage.input + tokenUsage.output) / 1000).toFixed(1)}k tokens
            </span>
          )}
        </div>
      </div>
    </div>
  )
})
