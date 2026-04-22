/**
 * Chat message utilities — parts-based model.
 *
 * Pure functions for building and transforming ChatMessage arrays.
 */

import type { ChatMessage, MessagePart, SSEEvent } from "@/lib/chat-types"

// ---------------------------------------------------------------------------
// SSE event application (immutable)
// ---------------------------------------------------------------------------

function emptyAssistantMessage(id: string): ChatMessage {
  return {
    id,
    role: "assistant",
    parts: [],
    createdAt: new Date(),
    streaming: true,
  }
}

function ensureAssistant(messages: ChatMessage[], messageId: string): [ChatMessage[], ChatMessage] {
  const existing = messages.find((message) => message.id === messageId)
  if (existing?.role === "assistant") {
    return [messages, existing]
  }
  const msg = emptyAssistantMessage(messageId)
  return [[...messages, msg], msg]
}

function replaceMessage(messages: ChatMessage[], updated: ChatMessage): ChatMessage[] {
  const index = messages.findIndex((message) => message.id === updated.id)
  if (index === -1) {
    return [...messages, updated]
  }
  return [...messages.slice(0, index), updated, ...messages.slice(index + 1)]
}

export function applySSEEvent(messages: ChatMessage[], event: SSEEvent): ChatMessage[] {
  switch (event.type) {
    case "text_delta": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const parts = [...last.parts]
      const lastTextIdx = parts.findLastIndex((p) => p.type === "text")
      if (lastTextIdx >= 0) {
        const prev = parts[lastTextIdx] as { type: "text"; text: string }
        parts[lastTextIdx] = { type: "text", text: prev.text + event.content }
      } else {
        parts.push({ type: "text", text: event.content })
      }
      return replaceMessage(msgs, { ...last, parts, streaming: true })
    }

    case "thinking_delta": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const parts = [...last.parts]
      const thinkIdx = parts.findIndex((p) => p.type === "thinking")
      if (thinkIdx >= 0) {
        const prev = parts[thinkIdx] as { type: "thinking"; text: string; isStreaming: boolean }
        parts[thinkIdx] = { type: "thinking", text: prev.text + event.content, isStreaming: true }
      } else {
        // Thinking goes first, before text parts
        parts.unshift({ type: "thinking", text: event.content, isStreaming: true })
      }
      return replaceMessage(msgs, { ...last, parts, streaming: true })
    }

    case "tool_call_start": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const part: MessagePart = {
        type: "tool-call",
        id: event.metadata.id,
        toolName: event.metadata.name,
        args: event.metadata.args,
        status: "running",
      }
      return replaceMessage(msgs, { ...last, parts: [...last.parts, part], streaming: true })
    }

    case "tool_call_progress": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const parts = last.parts.map((p) => {
        const matches =
          p.type === "tool-call" &&
          (
            (event.metadata.id && p.id === event.metadata.id) ||
            (!event.metadata.id && p.toolName === event.metadata.name && p.status === "running")
          )
        if (matches) {
          return {
            ...p,
            progressStatus: event.metadata.status,
            progressText: event.metadata.preview,
          }
        }
        return p
      })
      return replaceMessage(msgs, { ...last, parts, streaming: true })
    }

    case "tool_call_end": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const parts = last.parts.map((p) => {
        const matches =
          p.type === "tool-call" &&
          (
            (event.metadata.id && p.id === event.metadata.id) ||
            (!event.metadata.id && p.toolName === event.metadata.name && p.status === "running")
          )
        if (matches) {
          return {
            ...p,
            status: (event.metadata.is_error ? "error" : "done") as "done" | "error",
            result: event.metadata.result,
            resultData: event.metadata.result_json,
            durationMs: event.metadata.duration_ms,
          }
        }
        return p
      })
      return replaceMessage(msgs, { ...last, parts, streaming: true })
    }

    case "text": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const parts = [...last.parts]
      const lastTextIdx = parts.findLastIndex((p) => p.type === "text")
      if (lastTextIdx >= 0) {
        parts[lastTextIdx] = { type: "text", text: event.content }
      } else {
        parts.push({ type: "text", text: event.content })
      }
      return replaceMessage(msgs, { ...last, parts, streaming: false })
    }

    case "done": {
      const last = messages.find((message) => message.id === event.messageId)
      if (!last || last.role !== "assistant") return messages
      const parts = last.parts.map((p) =>
        p.type === "thinking" ? { ...p, isStreaming: false } : p,
      )
      return replaceMessage(messages, { ...last, parts, streaming: false })
    }

    case "approval_required": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      const part: MessagePart = {
        type: "approval",
        approvalId: event.metadata.approval_id,
        toolName: event.metadata.tool,
        toolInput: event.metadata.input,
        approvalType: event.metadata.approval_type,
        status: "pending",
        createdAt: new Date(),
        risk: event.metadata.risk,
      }
      return replaceMessage(msgs, { ...last, parts: [...last.parts, part], streaming: true })
    }

    case "error": {
      const [msgs, last] = ensureAssistant(messages, event.messageId)
      return replaceMessage(msgs, {
        ...last,
        parts: [...last.parts, { type: "text", text: event.content }],
        streaming: false,
      })
    }
  }
}

// ---------------------------------------------------------------------------
// Database message mapping
// ---------------------------------------------------------------------------

export function mapDbMessage(msg: {
  id: string
  role: string
  type: string
  content?: string | null
  metadata?: Record<string, unknown> | null
  created_at: string
}): ChatMessage | null {
  if (msg.type !== "text") return null

  const createdAt = msg.created_at
    ? new Date(
        msg.created_at.endsWith("Z") || msg.created_at.includes("+")
          ? msg.created_at
          : `${msg.created_at}Z`,
      )
    : new Date()

  const role: "user" | "assistant" = msg.role === "user" ? "user" : "assistant"
  const rawMetadata = (msg.metadata ?? {}) as Record<string, unknown>
  const rawParts = Array.isArray(rawMetadata.parts) ? rawMetadata.parts : null
  const parts = rawParts
    ? rawParts.flatMap((part): MessagePart[] => {
        if (!part || typeof part !== "object") return []
        const typedPart = part as Record<string, unknown>
        if (typedPart.type === "thinking" && typeof typedPart.text === "string") {
          return [{
            type: "thinking",
            text: typedPart.text,
            isStreaming: Boolean(typedPart.isStreaming),
          }]
        }
        if (typedPart.type === "tool-call" && typeof typedPart.id === "string") {
          return [{
            type: "tool-call",
            id: typedPart.id,
            toolName: typeof typedPart.toolName === "string" ? typedPart.toolName : "",
            args:
              typedPart.args && typeof typedPart.args === "object"
                ? (typedPart.args as Record<string, unknown>)
                : {},
            status:
              typedPart.status === "running" || typedPart.status === "error"
                ? typedPart.status
                : "done",
            result: typeof typedPart.result === "string" ? typedPart.result : undefined,
            resultData: typedPart.resultData,
            durationMs:
              typeof typedPart.durationMs === "number" ? typedPart.durationMs : undefined,
            progressText:
              typeof typedPart.progressText === "string" ? typedPart.progressText : undefined,
            progressStatus:
              typeof typedPart.progressStatus === "string" ? typedPart.progressStatus : undefined,
          }]
        }
        if (typedPart.type === "text" && typeof typedPart.text === "string") {
          return [{ type: "text", text: typedPart.text }]
        }
        if (typedPart.type === "approval" && typeof typedPart.approvalId === "string") {
          return [{
            type: "approval",
            approvalId: typedPart.approvalId,
            toolName: typeof typedPart.toolName === "string" ? typedPart.toolName : "",
            toolInput:
              typedPart.toolInput && typeof typedPart.toolInput === "object"
                ? (typedPart.toolInput as Record<string, unknown>)
                : {},
            approvalType: typeof typedPart.approvalType === "string" ? typedPart.approvalType : "",
            status:
              typedPart.status === "pending" || typedPart.status === "approved" ||
              typedPart.status === "rejected" || typedPart.status === "cancelled"
                ? typedPart.status
                : "pending",
            createdAt: typedPart.createdAt ? new Date(typedPart.createdAt as string) : new Date(),
            risk: typeof typedPart.risk === "string" ? typedPart.risk : undefined,
          }]
        }
        return []
      })
    : [{ type: "text" as const, text: (msg.content ?? "").trim() }]

  return {
    id: String(msg.id),
    role,
    parts,
    createdAt,
    streaming: Boolean(rawMetadata.streaming),
  }
}

// ---------------------------------------------------------------------------
// Message factory
// ---------------------------------------------------------------------------

export function createUserMessage(id: string, text: string): ChatMessage {
  return {
    id,
    role: "user",
    parts: [{ type: "text", text }],
    createdAt: new Date(),
  }
}
