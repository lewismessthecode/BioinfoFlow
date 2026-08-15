"use client"

import { cn } from "@/lib/utils"
import { Plus } from "@/lib/icons"
import type { AgentSessionSummary } from "@/lib/agent/client"
import type { Project } from "@/lib/types"
import { ProjectItem } from "./project-item"
import { ConversationItem } from "./conversation-item"

interface ProjectListProps {
  projects: Project[]
  inboxConversations: AgentSessionSummary[]
  defaultProjectId?: string
  expandedProjects: Set<string>
  projectConversations: Map<string, AgentSessionSummary[]>
  loadingProjects: Set<string>
  collapsed: boolean
  activeProjectId: string
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
          <Plus aria-hidden="true" className="h-3.5 w-3.5" />
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
            "space-y-0.5 transition-colors duration-150",
            inboxConversations.length === 0 && "h-0 overflow-hidden",
          )}
        >
          {inboxConversations.map((conversation, index) => (
            <ConversationItem
              key={conversation.id}
              conversation={conversation}
              projectId={defaultProjectId}
              index={index}
              isActive={activeConversationId === conversation.id}
              onSelect={onSelectConversation}
              onRename={onRenameConversation}
              onDelete={onDeleteConversation}
              canDelete={canDeleteWorkspaceResources}
              tSidebar={tSidebar}
              tCommon={tCommon}
            />
          ))}
        </div>
      ) : null}

      {projects.map((project) => (
        <ProjectItem
          key={project.id}
          project={project}
          isActive={project.id === activeProjectId}
          isExpanded={expandedProjects.has(project.id)}
          collapsed={false}
          conversations={projectConversations.get(project.id) || []}
          isLoadingConversations={loadingProjects.has(project.id)}
          activeConversationId={activeConversationId}
          onToggleExpand={onToggleExpand}
          onSelectProject={onSelectProject}
          onSelectConversation={onSelectConversation}
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
    </div>
  )
}
