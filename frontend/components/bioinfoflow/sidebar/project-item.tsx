"use client"

import { cn } from "@/lib/utils"
import { ChevronRight, FolderKanban, MoreVertical, Plus, Copy, Trash2 } from "@/lib/icons"
import { Button } from "@/components/ui/button"
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import type { AgentSessionSummary } from "@/lib/agent/client"
import type { Project } from "@/lib/types"
import { ConversationItem } from "./conversation-item"

interface ProjectItemProps {
  project: Project
  isActive: boolean
  isExpanded: boolean
  collapsed: boolean
  conversations: AgentSessionSummary[]
  isLoadingConversations: boolean
  activeConversationId: string
  onToggleExpand: (projectId: string) => void
  onSelectProject: (project: Project) => void
  onSelectConversation: (conversation: AgentSessionSummary, projectId: string) => void
  onCreateConversation: (projectId: string) => void
  onRenameConversation: (conversation: AgentSessionSummary, projectId: string, newTitle: string) => void
  onDeleteConversation: (conversationId: string, projectId: string, name: string) => void
  onRenameProject: (project: Project, newName: string) => void
  onDuplicateProject: (project: Project) => void
  onDeleteProject: (projectId: string, projectName: string) => void
  canDeleteWorkspaceResources?: boolean
  tSidebar: (key: string, values?: Record<string, string | number>) => string
  tCommon: (key: string) => string
}

export function ProjectItem({
  project,
  isActive,
  isExpanded,
  collapsed,
  conversations,
  isLoadingConversations,
  activeConversationId,
  onToggleExpand,
  onSelectProject,
  onSelectConversation,
  onCreateConversation,
  onRenameConversation,
  onDeleteConversation,
  onRenameProject,
  onDuplicateProject,
  onDeleteProject,
  canDeleteWorkspaceResources = true,
  tSidebar,
  tCommon,
}: ProjectItemProps) {
  const isRemoteProject = project.storage_mode === "remote"
  const handleProjectRowClick = () => {
    if (isActive && activeConversationId) {
      onSelectProject(project)
      return
    }
    if (isActive) {
      onToggleExpand(project.id)
      return
    }
    onSelectProject(project)
  }

  if (collapsed) {
    return (
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            onClick={() => onSelectProject(project)}
            aria-label={project.name}
            className={cn(
              "flex h-8 w-full items-center justify-center rounded-[7px] transition-[background-color,box-shadow,color,transform] duration-150 outline-none motion-safe:active:scale-[0.98] focus-visible:bg-sidebar-foreground/[0.06] focus-visible:ring-2 focus-visible:ring-sidebar-ring/45",
              isActive
                ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
                : "text-sidebar-foreground/78 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
            )}
          >
            <FolderKanban aria-hidden="true" className="h-3.5 w-3.5" />
          </button>
        </TooltipTrigger>
        <TooltipContent side="right" sideOffset={12}>{project.name}</TooltipContent>
      </Tooltip>
    )
  }

  return (
    <div className="transition-colors duration-150">
        {/* Project Header */}
      <div
        className={cn(
          "group flex min-h-[28px] items-center gap-1 rounded-[7px] border border-transparent px-1.5 py-1 text-[12px] transition-colors duration-150",
          isActive
            ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
            : "text-sidebar-foreground/82 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
        )}
      >
        <button
          onClick={handleProjectRowClick}
          className="flex min-w-0 flex-1 items-center gap-2 rounded-[6px] text-left outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring/45"
          aria-expanded={isExpanded}
        >
          <ChevronRight
            className={cn(
              "h-3 w-3 shrink-0 text-sidebar-foreground/62 transition-transform duration-150",
              isExpanded && "rotate-90"
            )}
          />
          <span
            className={cn(
              "flex h-5 w-5 shrink-0 items-center justify-center rounded-[5px] transition-colors duration-150",
              isActive
                ? "text-sidebar-foreground"
                : "text-sidebar-foreground/72"
            )}
          >
            <FolderKanban className="h-3.5 w-3.5 shrink-0" />
          </span>
          <span className={cn("truncate text-[12px] font-semibold", !isActive && "font-medium")}>{project.name}</span>
          {isRemoteProject ? (
            <span className="shrink-0 rounded-[5px] border border-sidebar-border/60 px-1 py-0.5 text-[9px] font-medium uppercase tracking-wide text-sidebar-foreground/64">
              {tSidebar("remoteProjectBadge")}
            </span>
          ) : null}
        </button>
        <Button
          variant="ghost"
          size="icon"
          className="h-5 w-5 shrink-0 rounded-[5px] opacity-0 transition-opacity hover:bg-sidebar-foreground/[0.055] group-hover:opacity-100 focus-visible:opacity-100"
          aria-label={tSidebar("newConversation")}
          onClick={(event) => {
            event.stopPropagation()
            onCreateConversation(project.id)
          }}
        >
          <Plus data-icon="inline-start" aria-hidden="true" className="h-3 w-3" />
        </Button>
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button
              variant="ghost"
              size="icon"
              className="h-5 w-5 shrink-0 rounded-[5px] opacity-0 transition-opacity hover:bg-sidebar-foreground/[0.055] group-hover:opacity-100 focus-visible:opacity-100"
              aria-label={tCommon("actions")}
              onClick={(event) => event.stopPropagation()}
            >
              <MoreVertical data-icon="inline-start" aria-hidden="true" className="h-3 w-3" />
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
              <Copy data-icon="inline-start" aria-hidden="true" />
              {tCommon("duplicate") || "Duplicate"}
            </DropdownMenuItem>
            {canDeleteWorkspaceResources ? (
              <>
                <DropdownMenuSeparator />
                <DropdownMenuItem
                  className="text-destructive"
                  onClick={() => onDeleteProject(project.id, project.name)}
                >
                  <Trash2 data-icon="inline-start" aria-hidden="true" />
                  {tCommon("delete")}
                </DropdownMenuItem>
              </>
            ) : null}
          </DropdownMenuContent>
        </DropdownMenu>
      </div>

      {/* Expanded Conversations */}
      {isExpanded && (isLoadingConversations || conversations.length > 0) ? (
        <div className="mt-1 space-y-0.5 pb-1 pl-6">
          {isLoadingConversations ? (
            <div className="px-2 py-1 text-[11px] text-muted-foreground">
              {tCommon("loading")}
            </div>
          ) : (
            conversations.map((conversation, index) => (
              <ConversationItem
                key={conversation.id}
                conversation={conversation}
                projectId={project.id}
                index={index}
                isActive={activeConversationId === conversation.id}
                onSelect={onSelectConversation}
                onRename={onRenameConversation}
                onDelete={onDeleteConversation}
                canDelete={canDeleteWorkspaceResources}
                tSidebar={tSidebar}
                tCommon={tCommon}
              />
            ))
          )}
        </div>
      ) : null}
    </div>
  )
}
