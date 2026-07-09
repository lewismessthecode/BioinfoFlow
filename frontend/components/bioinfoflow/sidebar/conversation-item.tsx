"use client"

import { useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { MessageSquare, MoreVertical, Trash2 } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { AgentCoreSession } from "@/lib/agent-core"

interface ConversationItemProps {
  conversation: AgentCoreSession
  projectId: string
  index: number
  isActive: boolean
  isDragging?: boolean
  onSelect: (conversation: AgentCoreSession, projectId: string) => void
  onDragStart?: (conversation: AgentCoreSession, projectId: string) => void
  onDragEnd?: () => void
  onRename: (conversation: AgentCoreSession, projectId: string, newTitle: string) => void
  onDelete: (conversationId: string, projectId: string, name: string) => void
  canDelete?: boolean
  tSidebar: (key: string, values?: Record<string, number>) => string
  tCommon: (key: string) => string
}

export function ConversationItem({
  conversation,
  projectId,
  index,
  isActive,
  isDragging = false,
  onSelect,
  onDragStart,
  onDragEnd,
  onRename,
  onDelete,
  canDelete = true,
  tSidebar,
  tCommon,
}: ConversationItemProps) {
  const [isEditing, setIsEditing] = useState(false)
  const [editValue, setEditValue] = useState("")
  const editInputRef = useRef<HTMLInputElement>(null)

  const label = conversation.title || tSidebar("conversationFallback", { index: index + 1 })

  const startRename = () => {
    setIsEditing(true)
    setEditValue(conversation.title || "")
    setTimeout(() => editInputRef.current?.select(), 0)
  }

  const commitRename = () => {
    setIsEditing(false)
    onRename(conversation, projectId, editValue)
  }

  return (
    <div
      draggable={false}
      onDragStart={(event) => {
        event.dataTransfer.effectAllowed = "move"
        event.dataTransfer.setData(
          "application/bioinfoflow-conversation",
          JSON.stringify({ id: conversation.id, projectId }),
        )
        onDragStart?.(conversation, projectId)
      }}
      onDragEnd={() => onDragEnd?.()}
      className={cn(
        "group flex items-center gap-1.5 rounded-[7px] border border-transparent px-2 py-1 text-[12px] leading-4 transition-colors duration-150",
        isActive
          ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground font-semibold"
          : "text-sidebar-foreground/78 font-medium hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground",
        isDragging && "opacity-45"
      )}
    >
      {isEditing ? (
        <div className="flex min-w-0 flex-1 items-center gap-1.5 text-[12px]">
          <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-primary" />
          <input
            ref={editInputRef}
            value={editValue}
            onChange={(e) => setEditValue(e.target.value)}
            onBlur={commitRename}
            onKeyDown={(e) => {
              if (e.key === "Enter") commitRename()
              if (e.key === "Escape") setIsEditing(false)
            }}
            className="min-w-0 flex-1 border-b border-primary bg-transparent py-0 outline-none"
            autoFocus
          />
        </div>
      ) : (
        <button
          onClick={() => onSelect(conversation, projectId)}
          onDoubleClick={startRename}
          className="flex min-w-0 flex-1 items-center gap-1.5 rounded-[6px] text-left text-[12px] outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring/45"
        >
          {isActive ? (
            <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-sidebar-foreground" />
          ) : (
            <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-sidebar-foreground/72" />
          )}
          <span className="truncate leading-snug py-0.5">{label}</span>
        </button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-6 w-6 rounded-[6px] opacity-0 transition-opacity hover:bg-sidebar-foreground/[0.055] group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100"
            aria-label={tCommon("actions")}
          >
            <MoreVertical className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={startRename}>
            {tCommon("edit")}
          </DropdownMenuItem>
          {canDelete ? (
            <>
              <DropdownMenuItem
                className="text-destructive"
                onClick={() => onDelete(conversation.id, projectId, label)}
              >
                <Trash2 className="h-3.5 w-3.5 mr-2" />
                {tCommon("delete")}
              </DropdownMenuItem>
            </>
          ) : null}
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
