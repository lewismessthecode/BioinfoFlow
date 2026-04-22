"use client"

import { memo, useMemo, useState, useRef, useEffect, useCallback } from "react"
import { Copy, RefreshCw, Pencil, Check, X } from "lucide-react"
import { toast } from "sonner"

import { Button } from "@/components/ui/button"
import { TextPart } from "./parts/text-part"
import { ThinkingPart } from "./parts/thinking-part"
import { ToolCallPart, ToolCallGroup } from "./parts/tool-call-part"
import { ApprovalPart } from "./parts/approval-part"
import type { ChatMessage, MessagePart, ToolCallPart as ToolCallPartType } from "@/lib/chat-types"

interface MessageBubbleProps {
  message: ChatMessage
  messageIndex?: number
  isLastUserMessage?: boolean
  onRegenerate?: () => void
  onResolveApproval?: (approvalId: string, action: "approve" | "reject") => void
  onEdit?: (messageIndex: number, newText: string) => void
}

/**
 * Group consecutive tool-call parts into arrays so they render
 * as a single collapsible "Used N tools" block.
 */
function groupParts(parts: MessagePart[]): (MessagePart | ToolCallPartType[])[] {
  const groups: (MessagePart | ToolCallPartType[])[] = []
  let toolBuffer: ToolCallPartType[] = []

  for (const part of parts) {
    if (part.type === "tool-call") {
      toolBuffer.push(part)
    } else {
      if (toolBuffer.length > 0) {
        groups.push(toolBuffer)
        toolBuffer = []
      }
      groups.push(part)
    }
  }
  if (toolBuffer.length > 0) groups.push(toolBuffer)
  return groups
}

export const MessageBubble = memo(function MessageBubble({
  message,
  messageIndex,
  isLastUserMessage,
  onRegenerate,
  onResolveApproval,
  onEdit,
}: MessageBubbleProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editText, setEditText] = useState("")
  const editRef = useRef<HTMLTextAreaElement>(null)

  const startEdit = useCallback(() => {
    const text = (message.parts[0]?.type === "text" ? message.parts[0].text : "").trim()
    setEditText(text)
    setIsEditing(true)
  }, [message.parts])

  useEffect(() => {
    if (isEditing) editRef.current?.focus()
  }, [isEditing])

  const commitEdit = useCallback(() => {
    setIsEditing(false)
    if (editText.trim() && messageIndex != null && onEdit) {
      onEdit(messageIndex, editText.trim())
    }
  }, [editText, messageIndex, onEdit])

  const grouped = useMemo(() => groupParts(message.parts), [message.parts])

  if (message.role === "user") {
    const text = (message.parts[0]?.type === "text" ? message.parts[0].text : "").trim()

    if (isEditing) {
      return (
        <div className="flex justify-end">
          <div className="max-w-[85%] w-full">
            <div className="rounded-2xl rounded-tr-sm border border-primary/30 bg-primary/5 px-4 py-2.5">
              <textarea
                ref={editRef}
                value={editText}
                onChange={(e) => setEditText(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); commitEdit() }
                  if (e.key === "Escape") setIsEditing(false)
                }}
                aria-label="Edit message"
                className="w-full resize-none bg-transparent text-[15px] leading-relaxed outline-none text-foreground min-h-[40px]"
                rows={Math.min(editText.split("\n").length, 6)}
              />
              <div className="flex items-center gap-1 mt-1 justify-end">
                <Button size="sm" variant="ghost" className="h-6 px-2 text-xs" onClick={() => setIsEditing(false)}>
                  <X className="h-3 w-3 mr-1" />Cancel
                </Button>
                <Button size="sm" className="h-6 px-2 text-xs" onClick={commitEdit} disabled={!editText.trim()}>
                  <Check className="h-3 w-3 mr-1" />Send
                </Button>
              </div>
            </div>
          </div>
        </div>
      )
    }

    return (
      <div className="flex justify-end">
        <div className="max-w-[85%]">
          <div className="rounded-2xl rounded-tr-sm bg-primary px-4 py-2.5 text-primary-foreground">
            <p className="text-[15px] leading-relaxed whitespace-pre-wrap break-words">
              {text}
            </p>
          </div>
          {isLastUserMessage && onEdit && (
            <div className="flex justify-end mt-0.5 opacity-0 group-hover:opacity-100 transition-opacity">
              <Button variant="ghost" size="sm" className="h-6 px-2 text-xs text-muted-foreground" onClick={startEdit}>
                <Pencil className="h-3 w-3 mr-1" />Edit
              </Button>
            </div>
          )}
        </div>
      </div>
    )
  }

  return (
    <div className="w-full space-y-2">
      {grouped.map((item, i) => {
        // Tool call group
        if (Array.isArray(item)) {
          return <ToolCallGroup key={`tools-${i}`} parts={item} />
        }
        // Single parts
        switch (item.type) {
          case "thinking":
            return <ThinkingPart key={`thinking-${i}`} part={item} />
          case "text":
            return <TextPart key={`text-${i}`} part={item} />
          case "tool-call":
            return <ToolCallPart key={`tool-${item.id}`} part={item} />
          case "approval":
            return (
              <ApprovalPart
                key={`approval-${item.approvalId}`}
                part={item}
                onResolve={onResolveApproval ?? (() => {})}
              />
            )
        }
      })}

      {/* Action bar — only for completed assistant messages */}
      {message.parts.some((p) => p.type === "text" && p.text) && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity">
          <Button
            variant="ghost"
            size="sm"
            className="h-7 px-2 text-xs text-muted-foreground"
            onClick={() => {
              const text = message.parts
                .filter((p) => p.type === "text")
                .map((p) => (p as { text: string }).text)
                .join("\n")
              navigator.clipboard.writeText(text).then(
                () => toast.success("Copied to clipboard"),
                () => toast.error("Failed to copy"),
              )
            }}
          >
            <Copy className="h-3 w-3 mr-1" />
            Copy
          </Button>
          {onRegenerate && (
            <Button
              variant="ghost"
              size="sm"
              className="h-7 px-2 text-xs text-muted-foreground"
              onClick={onRegenerate}
            >
              <RefreshCw className="h-3 w-3 mr-1" />
              Regenerate
            </Button>
          )}
        </div>
      )}
    </div>
  )
})
