"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { toast } from "sonner"

import { apiRequest, getApiErrorMessage } from "@/lib/api"
import { applySSEEvent, createClientMessageId, createUserMessage, mapDbMessage } from "@/lib/chat-utils"
import type { AgentChatStatus, ChatMessage, SSEEvent } from "@/lib/chat-types"
import type {
  AgentConversationHistory,
  AgentEventData,
  AgentMessageResponse,
  EventEnvelope,
  ExecutionPolicy,
} from "@/lib/types"
import { useEvents } from "@/hooks/use-events"
import { useChatScroll } from "@/hooks/use-chat-scroll"
import {
  clearStoredConversationId,
  emitConversationUpdated,
  getStoredConversationId,
  setStoredConversationId,
} from "@/lib/conversations"
import { useProjectContext } from "@/components/bioinfoflow/project-context"

const FALLBACK_TITLE_LENGTH = 60

const toFallbackConversationTitle = (text: string) => {
  const compact = text.trim().replace(/\s+/g, " ")
  if (compact.length <= FALLBACK_TITLE_LENGTH) return compact
  const snippet = compact.slice(0, FALLBACK_TITLE_LENGTH + 1)
  const trimmed = snippet.slice(0, snippet.lastIndexOf(" ")).trim()
  return `${(trimmed || compact.slice(0, FALLBACK_TITLE_LENGTH)).trim()}...`
}

export function useAgentChat(projectId?: string) {
  const {
    activeConversationId,
    setActiveConversationId,
    conversationProjectId,
    setConversationProjectId,
  } = useProjectContext()

  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [conversationId, setConversationId] = useState<string | null>(null)
  const [isLoading, setIsLoading] = useState(true)
  const [status, setStatus] = useState<AgentChatStatus>("idle")
  const [error, setError] = useState<Error | null>(null)
  const [currentActivity, setCurrentActivity] = useState<string | null>(null)
  const [executionPolicy, setExecutionPolicyState] =
    useState<ExecutionPolicy | null>(null)
  const currentActivityRef = useRef<string | null>(null)

  const updateActivity = useCallback((activity: string | null) => {
    if (currentActivityRef.current === activity) return
    currentActivityRef.current = activity
    setCurrentActivity(activity)
  }, [])
  const [tokenUsage, setTokenUsage] = useState<{ input: number; output: number; context: number } | null>(null)

  const messageIdsRef = useRef(new Set<string>())
  const messagesRef = useRef<ChatMessage[]>([])
  const approvalToolNamesRef = useRef<Record<string, string>>({})
  const activeResponseIdRef = useRef<string | null>(null)
  const isLoadingConversationRef = useRef(false)
  const eventBufferRef = useRef<EventEnvelope<AgentEventData>[]>([])
  const handleAgentEventRef = useRef<((envelope: EventEnvelope<AgentEventData>) => void) | null>(null)

  const { messagesEndRef, scrollContainerRef, scrollFabProps } = useChatScroll(messages)

  useEffect(() => {
    messagesRef.current = messages
  }, [messages])

  const refreshConversationTitle = useCallback(
    async (targetConversationId: string) => {
      if (!projectId) return

      for (let attempt = 0; attempt < 4; attempt += 1) {
        try {
          const { data } = await apiRequest<AgentConversationHistory>(
            `/agent/conversations/${targetConversationId}`,
          )
          if (data.title?.trim()) {
            emitConversationUpdated({
              id: data.conversation_id,
              project_id: data.project_id,
              title: data.title,
              pinned: data.pinned,
            })
            return
          }
        } catch {
          return
        }

        await new Promise((resolve) => setTimeout(resolve, 350))
      }
    },
    [projectId],
  )

  // ---- Conversation persistence ----
  const persistConversation = useCallback(
    (id: string) => {
      if (!projectId) return
      setStoredConversationId(projectId, id)
      setConversationId(id)
      setConversationProjectId(projectId)
      setActiveConversationId(id)
    },
    [projectId, setActiveConversationId, setConversationProjectId],
  )

  // ---- Load conversation from DB ----
  const loadConversation = useCallback(async () => {
    if (!projectId) {
      setMessages([])
      setConversationId(null)
      setIsLoading(false)
      return
    }

    setIsLoading(true)
    isLoadingConversationRef.current = true
    eventBufferRef.current = []
    messageIdsRef.current = new Set()

    const storedId = getStoredConversationId(projectId)
    const preferredId =
      conversationProjectId === projectId && activeConversationId
        ? activeConversationId
        : storedId
    let history: AgentConversationHistory | null = null

    if (preferredId) {
      try {
        const response = await apiRequest<AgentConversationHistory>(
          `/agent/conversations/${preferredId}`,
        )
        history = response.data
      } catch {
        clearStoredConversationId(projectId)
      }
    }

    if (history) {
      const mapped = history.messages
        .map((msg) => mapDbMessage(msg as Parameters<typeof mapDbMessage>[0]))
        .filter((m): m is ChatMessage => m !== null)

      for (const m of mapped) messageIdsRef.current.add(m.id)
      setMessages(mapped)
      setExecutionPolicyState(history.execution_policy ?? null)
      persistConversation(preferredId!)
      try {
        const statusResponse = await apiRequest<{
          conversation_id: string
          is_running: boolean
          assistant_message_id?: string | null
          response_id?: string | null
          last_event_at?: string | null
        }>(`/agent/conversations/${preferredId}/status`)
        activeResponseIdRef.current = statusResponse.data.response_id ?? null
        setStatus(statusResponse.data.is_running ? "streaming" : "idle")
      } catch {
        activeResponseIdRef.current = null
        setStatus("idle")
      }
    } else {
      setMessages([])
      setConversationId(null)
      setExecutionPolicyState(null)
      setStatus("idle")
    }

    setIsLoading(false)
    isLoadingConversationRef.current = false

    // Replay any SSE events that arrived during history load
    const buffered = eventBufferRef.current
    eventBufferRef.current = []
    for (const envelope of buffered) {
      handleAgentEventRef.current?.(envelope)
    }
  }, [projectId, activeConversationId, conversationProjectId, persistConversation])

  useEffect(() => {
    let cancelled = false

    queueMicrotask(() => {
      if (!cancelled) {
        void loadConversation()
      }
    })

    return () => {
      cancelled = true
    }
  }, [loadConversation])

  // ---- SSE event handler ----
  const handleAgentEvent = useCallback(
    (envelope: EventEnvelope<AgentEventData>) => {
      // Buffer events during history load — replay after load completes
      if (isLoadingConversationRef.current) {
        eventBufferRef.current.push(envelope)
        return
      }

      const convId = envelope.conversation_id
      if (convId && !conversationId) {
        persistConversation(convId)
      }
      if (convId && conversationId && convId !== conversationId) return

      const data = envelope.data
      const eventName = envelope.event

      // Map backend SSE event to our SSEEvent type
      let sseEvent: SSEEvent | null = null

      if (eventName === "agent.text_delta") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        sseEvent = { type: "text_delta", messageId: data.id, content: data.content || "" }
        updateActivity("Responding...")
      } else if (eventName === "agent.thinking_delta") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        sseEvent = { type: "thinking_delta", messageId: data.id, content: data.content || "" }
        updateActivity("Thinking...")
      } else if (eventName === "agent.tool_call_start") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        const toolName = (meta.name as string) || ""
        sseEvent = {
          type: "tool_call_start",
          messageId: data.id,
          metadata: {
            id: (meta.id as string) || "",
            name: toolName,
            args: (meta.args as Record<string, unknown>) || {},
          },
        }
        updateActivity(toolName ? `Running ${toolName}...` : "Running tool...")
      } else if (eventName === "agent.tool_call_progress") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        sseEvent = {
          type: "tool_call_progress",
          messageId: data.id,
          metadata: {
            id: (meta.id as string) || "",
            name: (meta.name as string) || "",
            status: (meta.status as string) || "",
            preview: (meta.preview as string) || data.content || "",
          },
        }
        updateActivity((meta.preview as string) || data.content || "Working...")
      } else if (eventName === "agent.tool_call_end") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        sseEvent = {
          type: "tool_call_end",
          messageId: data.id,
          metadata: {
            id: (meta.id as string) || "",
            name: (meta.name as string) || "",
            result: (meta.result as string) || "",
            result_json: meta.result_json,
            is_error: (meta.is_error as boolean) || false,
            duration_ms: (meta.duration_ms as number) || 0,
          },
        }
        updateActivity("Tool finished")
      } else if (eventName === "agent.message") {
        const meta = (data.metadata || {}) as Record<string, unknown>
        activeResponseIdRef.current = (meta.response_id as string) || activeResponseIdRef.current
        if (meta.requires_approval) {
          // Approval request — render as inline approval card
          sseEvent = {
            type: "approval_required",
            messageId: data.id,
            metadata: {
              approval_id: (meta.approval_id as string) || "",
              tool: (meta.tool as string) || "",
              input: (meta.input as Record<string, unknown>) || {},
              approval_type: (meta.approval_type as string) || "",
              risk: (meta.risk as string) || undefined,
            },
          }
        } else {
          if (data.id) messageIdsRef.current.add(data.id)
          sseEvent = { type: "text", messageId: data.id, content: data.content || "" }
        }
      } else if (eventName === "agent.approval.requested") {
        const payload = (data.payload || {}) as Record<string, unknown>
        const approvalId = (data.approval_id as string) || ""
        const approvalTool = (data.tool as string) || "clarify"
        if (approvalId) {
          approvalToolNamesRef.current[approvalId] = approvalTool
        }
        const responseId =
          (data.response_id as string) ||
          activeResponseIdRef.current ||
          approvalId ||
          ""
        if (responseId) {
          activeResponseIdRef.current = responseId
          sseEvent = {
            type: "approval_required",
            messageId: responseId,
            metadata: {
              approval_id: approvalId,
              tool: approvalTool,
              input:
                (payload.input as Record<string, unknown>) ||
                {
                  question: payload.question,
                  choices: payload.choices,
                },
              approval_type: (data.approval_type as string) || "clarify",
              risk: (payload.risk as string) || (data.risk as string) || undefined,
            },
          }
        }
      } else if (eventName === "agent.approval.resolved") {
        const approvalId = (data.approval_id as string) || ""
        const resolvedStatus = (data.status as string) || "approved"
        const resolvedToolName =
          approvalToolNamesRef.current[approvalId] ||
          (
            messagesRef.current
              .flatMap((message) => message.parts)
              .find((part) => part.type === "approval" && part.approvalId === approvalId)?.toolName
          ) ||
          ""
        setMessages((prev) =>
          prev.map((msg) => {
            let changed = false
            const parts = msg.parts.map((part) => {
              if (part.type === "approval" && part.approvalId === approvalId) {
                changed = true
                return {
                  ...part,
                  status:
                    resolvedStatus === "approved" || resolvedStatus === "rejected"
                      ? resolvedStatus
                      : part.status,
                }
              }
              if (
                part.type === "tool-call" &&
                part.status === "running" &&
                resolvedToolName &&
                part.toolName === resolvedToolName
              ) {
                changed = true
                const progressText =
                  resolvedStatus === "approved"
                    ? `Approval received, resuming ${resolvedToolName}`
                    : `Approval denied for ${resolvedToolName}`
                return {
                  ...part,
                  progressStatus: resolvedStatus,
                  progressText,
                }
              }
              return part
            })
            return changed ? { ...msg, parts } : msg
          }),
        )
        if (resolvedToolName) {
          if (resolvedStatus === "approved") {
            updateActivity(`Approval received, resuming ${resolvedToolName}`)
          } else if (resolvedStatus === "rejected") {
            updateActivity(`Approval denied for ${resolvedToolName}`)
          }
        } else if (resolvedStatus === "approved") {
          updateActivity("Approval received, resuming")
        } else if (resolvedStatus === "rejected") {
          updateActivity("Approval denied")
        }
        if (approvalId) {
          delete approvalToolNamesRef.current[approvalId]
        }
        return
      } else if (eventName === "agent.done") {
        sseEvent = { type: "done", messageId: data.id }
        activeResponseIdRef.current = null
        setStatus("idle")
        updateActivity(null)
        if (convId || conversationId) {
          void refreshConversationTitle(convId || conversationId!)
        }
        // Extract usage metadata if present
        const meta = (data.metadata || {}) as Record<string, unknown>
        if (meta.input_tokens || meta.output_tokens) {
          setTokenUsage({
            input: (meta.input_tokens as number) || 0,
            output: (meta.output_tokens as number) || 0,
            context: (meta.context_tokens as number) || 0,
          })
        }
      } else if (eventName === "agent.cancelled") {
        activeResponseIdRef.current = null
        setStatus("idle")
        updateActivity(null)
        // Clear in-flight part state so the spinner actually stops. Without
        // this, tool-call parts stay "running", thinking parts stay
        // isStreaming, and approval parts stay "pending" — the UI then
        // renders loading indicators forever even after agent.cancelled.
        setMessages((prev) =>
          prev.map((msg) => {
            if (!msg.streaming && msg.role !== "assistant") return msg
            let changed = false
            const parts = msg.parts.map((part) => {
              if (part.type === "tool-call" && part.status === "running") {
                changed = true
                return { ...part, status: "cancelled" as const }
              }
              if (part.type === "thinking" && part.isStreaming) {
                changed = true
                return { ...part, isStreaming: false }
              }
              if (part.type === "approval" && part.status === "pending") {
                changed = true
                return { ...part, status: "cancelled" as const }
              }
              return part
            })
            if (!changed && !msg.streaming) return msg
            return { ...msg, parts, streaming: false }
          }),
        )
        return
      } else if (eventName === "agent.error") {
        activeResponseIdRef.current = null
        sseEvent = {
          type: "error",
          messageId: data.id,
          content: data.content || "An error occurred",
        }
        setStatus("error")
        setError(new Error(data.content || "Agent error"))
        updateActivity(null)
      } else if (eventName === "agent.thinking" || eventName === "agent.thinking_content") {
        // Legacy thinking events — treat as thinking_delta for backward compat
        if (data.content) {
          sseEvent = { type: "thinking_delta", messageId: data.id, content: data.content }
        }
      }

      if (sseEvent) {
        setMessages((prev) => applySSEEvent(prev, sseEvent!))
      }
    },
    [conversationId, persistConversation, refreshConversationTitle, updateActivity],
  )

  // Keep ref in sync for buffer replay
  useEffect(() => {
    handleAgentEventRef.current = handleAgentEvent
  }, [handleAgentEvent])

  // ---- SSE subscription ----
  useEvents({
    projectId: projectId || null,
    conversationId,
    onAgentEvent: handleAgentEvent,
  })

  // ---- Send message ----
  const sendingRef = useRef(false)
  const sendMessage = useCallback(
    async (text: string, model?: string) => {
      if (!projectId || !text.trim() || sendingRef.current) return
      sendingRef.current = true
      const trimmedText = text.trim()
      const fallbackTitle = toFallbackConversationTitle(trimmedText)
      const isFirstPrompt = messages.length === 0

      const userMsg = createUserMessage(createClientMessageId(), trimmedText)
      setMessages((prev) => [...prev, userMsg])
      setStatus("streaming")
      setError(null)

      if (conversationId && isFirstPrompt) {
        emitConversationUpdated({
          id: conversationId,
          project_id: projectId,
          title: fallbackTitle,
        })
      }

      try {
        const payload: Record<string, string> = {
          project_id: projectId,
          content: trimmedText,
        }
        if (conversationId) payload.conversation_id = conversationId
        if (model) payload.model = model
        if (!conversationId && executionPolicy) {
          // The user can switch approval mode before the first message.
          // Persist that choice on the conversation that this send creates.
          payload.execution_policy = executionPolicy
        }

        const response = await apiRequest<AgentMessageResponse>(
          "/agent/message",
          { method: "POST", body: JSON.stringify(payload) },
        )
        const newConvId = response.data.conversation_id
        activeResponseIdRef.current = response.data.response_id ?? null
        if (newConvId && newConvId !== conversationId) {
          persistConversation(newConvId)
          if (isFirstPrompt) {
            emitConversationUpdated({
              id: newConvId,
              project_id: projectId,
              title: fallbackTitle,
            })
          }
        }
      } catch (err) {
        const message = getApiErrorMessage(err, "Failed to send message")
        toast.error(message)
        setStatus("error")
        setError(err instanceof Error ? err : new Error(message))
      } finally {
        sendingRef.current = false
      }
    },
    [projectId, conversationId, executionPolicy, messages.length, persistConversation],
  )

  // ---- Stop generation ----
  const stop = useCallback(async () => {
    if (!conversationId) return
    updateActivity("Cancelling...")
    try {
      await apiRequest(`/agent/conversations/${conversationId}/cancel`, { method: "POST" })
      updateActivity("Cancelled")
      setTimeout(() => updateActivity(null), 1500)
      setStatus("idle")
    } catch {
      try {
        const statusResponse = await apiRequest<{
          is_running: boolean
        }>(`/agent/conversations/${conversationId}/status`)
        if (statusResponse.data.is_running) {
          setStatus("streaming")
          updateActivity(null)
          toast.error("Failed to cancel — agent is still running")
        } else {
          setStatus("idle")
          updateActivity(null)
        }
      } catch {
        setStatus("idle")
        updateActivity(null)
      }
    }
  }, [conversationId, updateActivity])

  // ---- Regenerate last response ----
  const regenerate = useCallback(async () => {
    // Read messages via ref-stable accessor to avoid stale closure
    let userText: string | undefined
    setMessages((prev) => {
      const lastUserIdx = prev.findLastIndex((m) => m.role === "user")
      if (lastUserIdx === -1) return prev
      const lastUserMsg = prev[lastUserIdx]
      userText = lastUserMsg.parts.find((p) => p.type === "text")?.text
      return userText ? prev.slice(0, lastUserIdx) : prev
    })
    if (userText) await sendMessage(userText)
  }, [sendMessage])

  // ---- Edit last message and re-send ----
  const editAndResend = useCallback(
    async (messageIndex: number, newText: string) => {
      if (!newText.trim()) return
      // Use message ID for robustness against stale indices
      let targetId: string | undefined
      setMessages((prev) => {
        targetId = prev[messageIndex]?.id
        if (!targetId) return prev
        const idx = prev.findIndex((m) => m.id === targetId)
        return idx === -1 ? prev : prev.slice(0, idx)
      })
      if (targetId) await sendMessage(newText.trim())
    },
    [sendMessage],
  )

  // ---- Resolve approval ----
  const resolveApproval = useCallback(
    async (approvalId: string, action: "approve" | "reject") => {
      try {
        await apiRequest(`/agent/approvals/${approvalId}/resolve`, {
          method: "POST",
          body: JSON.stringify({ action }),
        })
        // Update the approval part status in the message list
        setMessages((prev) =>
          prev.map((msg) => {
            const updatedParts = msg.parts.map((p) =>
              p.type === "approval" && p.approvalId === approvalId
                ? { ...p, status: action === "approve" ? "approved" as const : "rejected" as const }
                : p,
            )
            return updatedParts === msg.parts ? msg : { ...msg, parts: updatedParts }
          }),
        )
      } catch (err) {
        const message = getApiErrorMessage(err, "Failed to resolve approval")
        toast.error(message)
      }
    },
    [],
  )

  // ---- New conversation ----
  const newConversation = useCallback(() => {
    if (projectId) clearStoredConversationId(projectId)
    setMessages([])
    setConversationId(null)
    if (projectId) {
      setConversationProjectId(projectId)
    }
    setActiveConversationId("")
    setStatus("idle")
    setError(null)
    setExecutionPolicyState(null)
    messageIdsRef.current = new Set()
  }, [projectId, setActiveConversationId, setConversationProjectId])

  // ---- Execution policy (Ask / Auto approve / Bypass) ----
  const setExecutionPolicy = useCallback(
    async (policy: ExecutionPolicy) => {
      if (!conversationId) {
        // No conversation yet — remember the user's intent so it applies to
        // whichever conversation is created next. The backend default stays
        // "auto", so if we never get to patch, the UX falls back safely.
        setExecutionPolicyState(policy)
        return
      }
      // Optimistic update; revert on failure.
      const prev = executionPolicy
      setExecutionPolicyState(policy)
      try {
        await apiRequest(`/agent/conversations/${conversationId}`, {
          method: "PATCH",
          body: JSON.stringify({ execution_policy: policy }),
        })
      } catch (err) {
        setExecutionPolicyState(prev)
        throw err
      }
    },
    [conversationId, executionPolicy],
  )

  return {
    messages,
    conversationId,
    isLoading,
    status,
    error,
    currentActivity,
    tokenUsage,
    executionPolicy,
    setExecutionPolicy,
    sendMessage,
    stop,
    regenerate,
    editAndResend,
    resolveApproval,
    newConversation,
    messagesEndRef,
    scrollContainerRef,
    scrollFabProps,
  }
}
