"use client"

import { cn } from "@/lib/utils"
import { ChevronRight, FolderKanban, MoreVertical, Plus, Copy, Trash2 } from "lucide-react"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { Project, AgentConversationRead } from "@/lib/types"
import { ConversationItem } from "./conversation-item"

interface ProjectItemProps {
  project: Project
  isActive: boolean
  isExpanded: boolean
  collapsed: boolean
  isDropTarget?: boolean
  conversations: AgentConversationRead[]
  isLoadingConversations: boolean
  activeConversationId: string
  onToggleExpand: (projectId: string) => void
  onSelectProject: (project: Project) => void
  onSelectConversation: (conversation: AgentConversationRead, projectId: string) => void
  onConversationDragStart: (conversation: AgentConversationRead, projectId: string) => void
  onConversationDragEnd: () => void
  onConversationDrop: (projectId: string) => void
  onConversationDragOver: (projectId: string) => void
  onConversationDragLeave: (projectId: string) => void
  onCreateConversation: (projectId: string) => void
  onRenameConversation: (conversation: AgentConversationRead, projectId: string, newTitle: string) => void
  onTogglePin: (conversation: AgentConversationRead, projectId: string) => void
  onDeleteConversation: (conversationId: string, projectId: string, name: string) => void
  onRenameProject: (project: Project, newName: string) => void
  onDuplicateProject: (project: Project) => void
  onDeleteProject: (projectId: string, projectName: string) => void
  tSidebar: (key: string, values?: Record<string, string | number>) => string
  tCommon: (key: string) => string
}

export function ProjectItem({
  project,
  isActive,
  isExpanded,
  collapsed,
  isDropTarget = false,
  conversations,
  isLoadingConversations,
  activeConversationId,
  onToggleExpand,
  onSelectProject,
  onSelectConversation,
  onConversationDragStart,
  onConversationDragEnd,
  onConversationDrop,
  onConversationDragOver,
  onConversationDragLeave,
  onCreateConversation,
  onRenameConversation,
  onTogglePin,
  onDeleteConversation,
  onRenameProject,
  onDuplicateProject,
  onDeleteProject,
  tSidebar,
  tCommon,
}: ProjectItemProps) {
  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => onSelectProject(project)}
            className={cn(
              "flex w-full h-9 items-center justify-center rounded-lg transition-colors",
              isActive
                ? "border border-sidebar-border/55 bg-sidebar-accent/75 text-sidebar-foreground"
                : "text-sidebar-foreground/78 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
            )}
          >
            <FolderKanban className="h-4 w-4" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right">{project.name}</TooltipContent>
      </Tooltip>
    )
  }

  return (
    <div
      className={cn(
        "rounded-2xl transition-colors duration-150",
        isDropTarget && "bg-sidebar-accent/20 ring-1 ring-sidebar-border/45"
      )}
      onDragOver={(event) => {
        event.preventDefault()
        onConversationDragOver(project.id)
      }}
      onDragLeave={() => onConversationDragLeave(project.id)}
      onDrop={(event) => {
        event.preventDefault()
        onConversationDrop(project.id)
      }}
    >
      {/* Project Header */}
      <div
        className={cn(
          "group flex items-center gap-1 rounded-xl border border-transparent px-2 py-1.5 text-sm transition-colors duration-150",
          isActive
            ? "border-sidebar-border/55 bg-sidebar-accent/75 text-sidebar-foreground"
            : "text-sidebar-foreground/82 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
        )}
      >
        <button
          onClick={() => onToggleExpand(project.id)}
          className="flex shrink-0 items-center rounded-lg p-1 transition-colors hover:bg-sidebar-accent/45"
          aria-label={isExpanded ? "Collapse" : "Expand"}
        >
          <ChevronRight
            className={cn(
              "h-3.5 w-3.5 transition-transform duration-150",
              isExpanded && "rotate-90"
            )}
          />
        </button>
        <button
          onClick={() => onSelectProject(project)}
          className="flex min-w-0 flex-1 items-center gap-2.5"
        >
          <span
            className={cn(
              "flex h-6 w-6 shrink-0 items-center justify-center rounded-md transition-colors duration-150",
              isActive
                ? "text-sidebar-foreground"
                : "text-sidebar-foreground/72"
            )}
          >
            <FolderKanban className="h-3.5 w-3.5 shrink-0" />
          </span>
          <span className={cn("truncate text-sm font-semibold", !isActive && "font-medium")}>{project.name}</span>
        </button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-6 w-6 opacity-0 group-hover:opacity-100 focus-visible:opacity-100 transition-opacity shrink-0"
              aria-label={tCommon("actions")}
            >
              <MoreVertical className="h-3 w-3" />
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem
              onClick={() => {
                const newName = window.prompt(tSidebar("prompts.renameProject"), project.name)
                if (newName) onRenameProject(project, newName)
              }}
            >
              {tSidebar("renameProject")}
            </DropdownMenuItem>
            <DropdownMenuItem onClick={() => onDuplicateProject(project)}>
              <Copy className="h-3.5 w-3.5 mr-2" />
              {tCommon("duplicate") || "Duplicate"}
            </DropdownMenuItem>
            <DropdownMenuSeparator />
            <DropdownMenuItem
              className="text-destructive"
              onClick={() => onDeleteProject(project.id, project.name)}
            >
              <Trash2 className="h-3.5 w-3.5 mr-2" />
              {tCommon("delete")}
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Expanded Conversations */}
      {isExpanded && (
        <div className="ml-3 mt-0.5 space-y-0.5 border-l border-border/35 pl-2.5 pb-1.5">
          {isLoadingConversations ? (
            <div className="px-2 py-1.5 text-xs text-muted-foreground">
              {tCommon("loading")}
            </div>
          ) : conversations.length === 0 ? (
            <div className="px-2 py-1.5 text-xs text-muted-foreground">
              {tSidebar("noConversations")}
            </div>
          ) : (
            conversations.map((conversation, index) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                projectId={project.id}
                index={index}
                isActive={activeConversationId === conversation.id}
                onDragStart={onConversationDragStart}
                onDragEnd={onConversationDragEnd}
                onSelect={onSelectConversation}
                onRename={onRenameConversation}
                onTogglePin={onTogglePin}
                onDelete={onDeleteConversation}
                tSidebar={tSidebar}
                tCommon={tCommon}
              />
            ))
          )}
          <button
            onClick={() => onCreateConversation(project.id)}
            className="flex w-full items-center gap-2 rounded-lg px-2 py-1 text-xs font-medium text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent/42 hover:text-sidebar-foreground"
          >
            <Plus className="h-3 w-3" />
            <span>{tSidebar("newConversation")}</span>
          </button>
        </div>
      )}
    </div>
  )
}
