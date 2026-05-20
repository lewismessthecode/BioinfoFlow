"use client"

import { useRef, useState } from "react"
import { cn } from "@/lib/utils"
import { MessageSquare, MoreVertical, Pin, PinOff, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import type { AgentConversationRead } from "@/lib/types"

interface ConversationItemProps {
  conversation: AgentConversationRead
  projectId: string
  index: number
  isActive: boolean
  isDragging?: boolean
  onSelect: (conversation: AgentConversationRead, projectId: string) => void
  onDragStart?: (conversation: AgentConversationRead, projectId: string) => void
  onDragEnd?: () => void
  onRename: (conversation: AgentConversationRead, projectId: string, newTitle: string) => void
  onTogglePin: (conversation: AgentConversationRead, projectId: string) => void
  onDelete: (conversationId: string, projectId: string, name: string) => void
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
  onTogglePin,
  onDelete,
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
      draggable={!isEditing}
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
        "group flex items-center gap-2 rounded-full border border-transparent px-3 py-1.5 text-sm transition-colors duration-150",
        isActive
          ? "bg-sidebar-accent text-sidebar-foreground font-semibold"
          : "text-sidebar-foreground/78 font-medium hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
        isDragging && "opacity-45"
      )}
    >
      {isEditing ? (
        <div className="flex flex-1 items-center gap-2 text-sm-tight min-w-0">
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
            className="flex-1 min-w-0 bg-transparent outline-none border-b border-primary py-0"
            autoFocus
          />
        </div>
      ) : (
        <button
          onClick={() => onSelect(conversation, projectId)}
          onDoubleClick={startRename}
          className="flex flex-1 items-center gap-2 text-left text-sm-tight min-w-0"
        >
          {isActive ? (
            <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-sidebar-foreground" />
          ) : (
            <MessageSquare className="h-3.5 w-3.5 flex-shrink-0 text-sidebar-foreground/72" />
          )}
          <span className="truncate leading-snug py-0.5">{label}</span>
          {conversation.pinned && <Pin className="h-3 w-3 text-muted-foreground flex-shrink-0 ml-auto" />}
        </button>
      )}
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button
            variant="ghost"
            size="icon"
            className="h-7 w-7 rounded-full opacity-0 group-hover:opacity-100 focus-visible:opacity-100 group-focus-within:opacity-100 transition-opacity hover:bg-white/70 dark:hover:bg-white/10"
            aria-label={tCommon("actions")}
          >
            <MoreVertical className="h-3 w-3" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onClick={startRename}>
            {tCommon("edit")}
          </DropdownMenuItem>
          <DropdownMenuItem onClick={() => onTogglePin(conversation, projectId)}>
            {conversation.pinned ? (
              <span className="flex items-center gap-2"><PinOff className="h-3.5 w-3.5" />{tCommon("clear")}</span>
            ) : (
              <span className="flex items-center gap-2"><Pin className="h-3.5 w-3.5" />{tCommon("save")}</span>
            )}
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem
            className="text-destructive"
            onClick={() => onDelete(conversation.id, projectId, label)}
          >
            <Trash2 className="h-3.5 w-3.5 mr-2" />
            {tCommon("delete")}
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
    </div>
  )
}
