"use client"

import { useState } from "react"
import { cn } from "@/lib/utils"
import { Plus } from "lucide-react"
import type { Project, AgentConversationRead } from "@/lib/types"
import { ProjectItem } from "./project-item"
import { ConversationItem } from "./conversation-item"

interface ProjectListProps {
  projects: Project[]
  inboxConversations: AgentConversationRead[]
  defaultProjectId?: string
  expandedProjects: Set<string>
  projectConversations: Map<string, AgentConversationRead[]>
  loadingProjects: Set<string>
  collapsed: boolean
  activeProjectId: string
  activeConversationId: string
  onToggleExpand: (projectId: string) => void
  onSelectProject: (project: Project) => void
  onSelectConversation: (conversation: AgentConversationRead, projectId: string) => void
  onMoveConversation: (conversationId: string, fromProjectId: string, targetProjectId: string) => void
  onCreateConversation: (projectId: string) => void
  onRenameConversation: (conversation: AgentConversationRead, projectId: string, newTitle: string) => void
  onTogglePin: (conversation: AgentConversationRead, projectId: string) => void
  onDeleteConversation: (conversationId: string, projectId: string, name: string) => void
  onRenameProject: (project: Project, newName: string) => void
  onDuplicateProject: (project: Project) => void
  onDeleteProject: (projectId: string, projectName: string) => void
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
  onTogglePin,
  onDeleteConversation,
  onRenameProject,
  onDuplicateProject,
  onDeleteProject,
  onOpenCreateDialog,
  tSidebar,
  tCommon,
}: ProjectListProps) {
  const [draggingConversation, setDraggingConversation] = useState<{
    id: string
    projectId: string
  } | null>(null)
  const [dropTargetProjectId, setDropTargetProjectId] = useState<string | null>(null)

  const handleConversationDragStart = (conversation: AgentConversationRead, projectId: string) => {
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
            onTogglePin={onTogglePin}
            onDeleteConversation={onDeleteConversation}
            onRenameProject={onRenameProject}
            onDuplicateProject={onDuplicateProject}
            onDeleteProject={onDeleteProject}
            tSidebar={tSidebar}
            tCommon={tCommon}
          />
        ))}
        <button
          onClick={onOpenCreateDialog}
          aria-label={tSidebar("newProject")}
          className="flex h-10 w-full items-center justify-center rounded-xl text-sidebar-foreground/78 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        >
          <Plus className="h-4 w-4" />
        </button>
      </div>
    )
  }

  return (
    <div className="space-y-1.5">
      {defaultProjectId ? (
        <div
          data-testid="sidebar-recent-section"
          className={cn(
            "rounded-xl px-1 py-1 transition-colors duration-150",
            dropTargetProjectId === defaultProjectId && "bg-sidebar-accent/20 ring-1 ring-sidebar-border/45"
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
          <div className="px-1.5 pb-1.5 text-[11px] font-semibold uppercase tracking-[0.16em] text-sidebar-foreground/55">
            {tSidebar("recent")}
          </div>
          <div className="space-y-0.5">
            {inboxConversations.length === 0 ? (
              <div className="px-2.5 py-1 text-xs text-muted-foreground">
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
                  onTogglePin={onTogglePin}
                  onDelete={onDeleteConversation}
                  tSidebar={tSidebar}
                  tCommon={tCommon}
                />
              ))
            )}
          </div>
        </div>
      ) : null}

      {projects.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-border/70 bg-[linear-gradient(180deg,rgba(148,163,184,0.08),transparent)] px-3 py-3 dark:bg-[linear-gradient(180deg,rgba(148,163,184,0.06),transparent)]">
          <p className="text-sm font-semibold text-foreground">{tSidebar("noProjects")}</p>
          <p className="mt-1.5 text-xs leading-relaxed text-muted-foreground">
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
          onTogglePin={onTogglePin}
          onDeleteConversation={onDeleteConversation}
          onRenameProject={onRenameProject}
          onDuplicateProject={onDuplicateProject}
          onDeleteProject={onDeleteProject}
          tSidebar={tSidebar}
          tCommon={tCommon}
        />
      ))}

      {/* New Project button */}
      <button
        onClick={onOpenCreateDialog}
        className={cn(
          "flex w-full items-center gap-3 rounded-lg px-2 py-1.5 text-sm font-semibold text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/55 hover:text-sidebar-foreground",
        )}
      >
        <span className="flex h-6 w-6 items-center justify-center rounded-md text-sidebar-foreground/76">
          <Plus className="h-4 w-4" />
        </span>
        <span>{tSidebar("newProject")}</span>
      </button>
    </div>
  )
}
