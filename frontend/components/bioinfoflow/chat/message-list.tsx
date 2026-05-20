"use client"

import { FolderKanban, Loader2 } from "lucide-react"
import { useTranslations } from "next-intl"

import { MessageBubble } from "./message-bubble"
import { TypingIndicator } from "./typing-indicator"
import { ChatErrorBoundary } from "./chat-error-boundary"
import type { AgentChatStatus, ChatMessage } from "@/lib/chat-types"

export interface MessageListProps {
  messages: ChatMessage[]
  status: AgentChatStatus
  isLoading: boolean
  projectId?: string
  messagesEndRef: React.RefObject<HTMLDivElement | null>
  onRegenerate: () => void
  onResolveApproval?: (approvalId: string, action: "approve" | "reject") => void
  onEdit?: (messageIndex: number, newText: string) => void
}

export function MessageList({
  messages,
  status,
  isLoading,
  projectId,
  messagesEndRef,
  onRegenerate,
  onResolveApproval,
  onEdit,
}: MessageListProps) {
  const tChat = useTranslations("chat")

  if (!projectId) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <div className="rounded-3xl border border-border/70 bg-white/70 p-8 flex flex-col items-center gap-3 text-center shadow-[0_12px_40px_rgba(60,64,67,0.08)] dark:bg-white/[0.04]">
          <div className="flex h-12 w-12 items-center justify-center rounded-full bg-secondary">
            <FolderKanban className="h-6 w-6 text-muted-foreground" />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">{tChat("selectProject")}</p>
            <p className="text-xs text-muted-foreground mt-1">
              Choose a project from the sidebar to start chatting
            </p>
          </div>
        </div>
      </div>
    )
  }

  if (isLoading) {
    return (
      <div className="mx-auto max-w-3xl px-4 py-12">
        <div className="rounded-3xl border border-border/70 bg-white/70 p-6 flex justify-center shadow-[0_12px_40px_rgba(60,64,67,0.08)] dark:bg-white/[0.04]">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      </div>
    )
  }

  if (messages.length === 0) return null

  const lastMessage = messages[messages.length - 1]
  const assistantHasVisibleContent = (message: ChatMessage) =>
    message.parts.some((part) => {
      if (part.type === "text" || part.type === "thinking") {
        return Boolean(part.text.trim())
      }
      return true
    })

  const showTyping =
    status === "streaming" &&
    messages.length > 0 &&
    (lastMessage.role === "user" ||
      (lastMessage.role === "assistant" && !assistantHasVisibleContent(lastMessage)))

  const lastUserIndex = messages.findLastIndex((m) => m.role === "user")

  return (
    <div className="mx-auto max-w-3xl px-4 py-8">
      <div className="space-y-6" aria-live="polite" aria-atomic="false">
        {messages.map((msg, i) => (
          <div key={msg.id} className="group">
            <ChatErrorBoundary label="message">
              <MessageBubble
                message={msg}
                messageIndex={i}
                isLastUserMessage={msg.role === "user" && i === lastUserIndex}
                onRegenerate={
                  msg.role === "assistant" && i === messages.length - 1
                    ? onRegenerate
                    : undefined
                }
                onResolveApproval={onResolveApproval}
                onEdit={onEdit}
              />
            </ChatErrorBoundary>
          </div>
        ))}
        {showTyping && <TypingIndicator />}
        <div ref={messagesEndRef} />
      </div>
    </div>
  )
}
