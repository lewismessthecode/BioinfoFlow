"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Plus } from "lucide-react"
import type { AgentCoreSession } from "@/lib/agent-core"
import type { Project } from "@/lib/types"
import { ProjectItem } from "./project-item"
import { ConversationItem } from "./conversation-item"

interface ProjectListProps {
  projects: Project[]
  inboxConversations: AgentCoreSession[]
  defaultProjectId?: string
  expandedProjects: Set<string>
  projectConversations: Map<string, AgentCoreSession[]>
  loadingProjects: Set<string>
  collapsed: boolean
  activeProjectId: string
  activeConversationId: string
  onToggleExpand: (projectId: string) => void
  onSelectProject: (project: Project) => void
  onSelectConversation: (conversation: AgentCoreSession, projectId: string) => void
  onMoveConversation: (conversationId: string, fromProjectId: string, targetProjectId: string) => void
  onCreateConversation: (projectId: string) => void
  onRenameConversation: (conversation: AgentCoreSession, projectId: string, newTitle: string) => void
  onDeleteConversation: (conversationId: string, projectId: string, name: string) => void
  onRenameProject: (project: Project, newName: string) => void
  onDuplicateProject: (project: Project) => void
  onDeleteProject: (projectId: string, projectName: string) => void
  canDeleteWorkspaceResources?: boolean
  onOpenCreateDialog: () => void
  tSidebar: (key: string, values?: Record<string, string | number>) => string
  tCommon: (key: string) => string
}

export function ProjectList({
  projects,
  inboxConversations,
  defaultProjectId,
  expandedProjects,
  projectConversations,
  loadingProjects,
  collapsed,
  activeProjectId,
  activeConversationId,
  onToggleExpand,
  onSelectProject,
  onSelectConversation,
  onMoveConversation,
  onCreateConversation,
  onRenameConversation,
  onDeleteConversation,
  onRenameProject,
  onDuplicateProject,
  onDeleteProject,
  canDeleteWorkspaceResources = true,
  onOpenCreateDialog,
  tSidebar,
  tCommon,
}: ProjectListProps) {
  const [draggingConversation, setDraggingConversation] = useState<{
    id: string
    projectId: string
  } | null>(null)
  const [dropTargetProjectId, setDropTargetProjectId] = useState<string | null>(null)

  const showRecentEmptyState = inboxConversations.length === 0 && projects.length === 0

  const handleConversationDragStart = (conversation: AgentCoreSession, projectId: string) => {
    setDraggingConversation({ id: conversation.id, projectId })
  }

  const handleConversationDragEnd = () => {
    setDraggingConversation(null)
    setDropTargetProjectId(null)
  }

  const handleConversationDragOver = (projectId: string) => {
    if (!draggingConversation || draggingConversation.projectId === projectId) return
    setDropTargetProjectId(projectId)
  }

  const handleConversationDragLeave = (projectId: string) => {
    setDropTargetProjectId((current) => (current === projectId ? null : current))
  }

  const handleConversationDrop = (projectId: string) => {
    if (!draggingConversation) return
    setDropTargetProjectId(null)
    if (draggingConversation.projectId !== projectId) {
      onMoveConversation(draggingConversation.id, draggingConversation.projectId, projectId)
    }
    setDraggingConversation(null)
  }

  if (collapsed) {
    return (
      <div className="space-y-1">
        {projects.map((project) => (
          <ProjectItem
            key={project.id}
            project={project}
            isActive={project.id === activeProjectId}
            isExpanded={false}
            collapsed
            conversations={[]}
            isLoadingConversations={false}
            activeConversationId={activeConversationId}
            onToggleExpand={onToggleExpand}
            onSelectProject={onSelectProject}
            onSelectConversation={onSelectConversation}
            onConversationDragStart={handleConversationDragStart}
            onConversationDragEnd={handleConversationDragEnd}
            onConversationDrop={handleConversationDrop}
            onConversationDragOver={handleConversationDragOver}
            onConversationDragLeave={handleConversationDragLeave}
            onCreateConversation={onCreateConversation}
            onRenameConversation={onRenameConversation}
            onDeleteConversation={onDeleteConversation}
            onRenameProject={onRenameProject}
            onDuplicateProject={onDuplicateProject}
            onDeleteProject={onDeleteProject}
            canDeleteWorkspaceResources={canDeleteWorkspaceResources}
            tSidebar={tSidebar}
            tCommon={tCommon}
          />
        ))}
        <button
          onClick={onOpenCreateDialog}
          aria-label={tSidebar("newProject")}
          className="flex h-8 w-full items-center justify-center rounded-[7px] text-sidebar-foreground/78 transition-colors hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
        >
          <Plus className="h-3.5 w-3.5" />
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-1">
      {defaultProjectId ? (
        <div
          data-testid="sidebar-recent-section"
          className={cn(
            "py-0.5 transition-colors duration-150",
            dropTargetProjectId === defaultProjectId && "rounded-[8px] bg-sidebar-foreground/[0.04] ring-1 ring-sidebar-border/45"
          )}
          onDragOver={(event) => {
            event.preventDefault()
            handleConversationDragOver(defaultProjectId)
          }}
          onDragLeave={() => handleConversationDragLeave(defaultProjectId)}
          onDrop={(event) => {
            event.preventDefault()
            handleConversationDrop(defaultProjectId)
          }}
        >
          <div className="px-2 pb-1 pt-0.5 text-[11px] font-medium text-sidebar-foreground/58">
            {tSidebar("recent")}
          </div>
          <div className="space-y-0.5">
            {showRecentEmptyState ? (
              <div className="px-2 py-1 text-[11px] text-muted-foreground">
                {tSidebar("noConversations")}
              </div>
            ) : (
              inboxConversations.map((conversation, index) => (
                <ConversationItem
                  key={conversation.id}
                  conversation={conversation}
                  projectId={defaultProjectId}
                  index={index}
                  isActive={activeConversationId === conversation.id}
                  isDragging={draggingConversation?.id === conversation.id}
                  onDragStart={handleConversationDragStart}
                  onDragEnd={handleConversationDragEnd}
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
        </div>
      ) : null}

      {projects.length === 0 ? (
        <div className="px-2.5 py-1.5">
          <p className="text-[12px] font-medium text-sidebar-foreground/72">{tSidebar("noProjects")}</p>
          <p className="mt-1 text-[11px] leading-4 text-muted-foreground">
            {tSidebar("noProjectsDescription")}
          </p>
        </div>
      ) : null}

      {projects.map((project) => (
        <ProjectItem
          key={project.id}
          project={project}
          isActive={project.id === activeProjectId}
          isExpanded={expandedProjects.has(project.id)}
          collapsed={false}
          isDropTarget={dropTargetProjectId === project.id}
          conversations={projectConversations.get(project.id) || []}
          isLoadingConversations={loadingProjects.has(project.id)}
          activeConversationId={activeConversationId}
          onToggleExpand={onToggleExpand}
          onSelectProject={onSelectProject}
          onSelectConversation={onSelectConversation}
          onConversationDragStart={handleConversationDragStart}
          onConversationDragEnd={handleConversationDragEnd}
          onConversationDrop={handleConversationDrop}
          onConversationDragOver={handleConversationDragOver}
          onConversationDragLeave={handleConversationDragLeave}
          onCreateConversation={onCreateConversation}
          onRenameConversation={onRenameConversation}
          onDeleteConversation={onDeleteConversation}
          onRenameProject={onRenameProject}
          onDuplicateProject={onDuplicateProject}
          onDeleteProject={onDeleteProject}
          canDeleteWorkspaceResources={canDeleteWorkspaceResources}
          tSidebar={tSidebar}
          tCommon={tCommon}
        />
      ))}

      {/* New Project button */}
      <button
        onClick={onOpenCreateDialog}
        className={cn(
          "flex h-[28px] w-full items-center gap-2 rounded-[7px] px-2.5 text-[12px] font-medium text-sidebar-foreground/78 transition-colors hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground",
        )}
      >
        <span className="flex h-4 w-4 items-center justify-center rounded-[5px] text-sidebar-foreground/72">
          <Plus className="h-3.5 w-3.5" />
        </span>
        <span>{tSidebar("newProject")}</span>
      </button>
    </div>
  )
}
