"use client"

import { useState, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import Link from "next/link"
import { ChevronRight, PanelLeftClose, PanelLeftOpen, Plus, Search, SquarePen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { UserMenu } from "@/components/bioinfoflow/user-menu"
import { CreateProjectDialog } from "@/components/bioinfoflow/create-project-dialog"
import { Logo } from "@/components/bioinfoflow/logo"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import {
  canManageDestructiveBusinessActions,
  type ViewerIdentity,
} from "@/lib/auth-config"
import { SidebarNav } from "./sidebar-nav"
import { ProjectList } from "./project-list"
import { DeleteConfirmDialog } from "./delete-confirm-dialog"

interface SidebarProps {
  collapsed: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  onCommandOpen?: () => void
  runtimeMode?: unknown
  viewer?: ViewerIdentity
}

export function Sidebar({ collapsed, onCollapsedChange, onCommandOpen, viewer }: SidebarProps) {
  const router = useRouter()
  const { activeProjectId, activeConversationId } = useProjectContext()
  const tSidebar = useTranslations("sidebar")
  const tCommon = useTranslations("common")
  const [workspaceExpanded, setWorkspaceExpanded] = useState(true)
  const [deleteConfirm, setDeleteConfirm] = useState<{
    type: "project" | "conversation"
    id: string
    projectId: string
    name: string
  } | null>(null)

  const workspaceShell = useWorkspaceShell()
  const canDeleteWorkspaceResources = viewer
    ? canManageDestructiveBusinessActions(
        viewer.mode,
        viewer.role,
        viewer.authEnabled,
      )
    : true

  const canCreateChat = !workspaceShell.isLoading

  const handleNewConversation = () => {
    if (canCreateChat) {
      workspaceShell.handleCreateConversation(activeProjectId || undefined)
      return
    }

    router.push("/agent")
  }

  const handleDeleteConversation = (conversationId: string, projectId: string, name: string) => {
    if (!canDeleteWorkspaceResources) return
    setDeleteConfirm({ type: "conversation", id: conversationId, projectId, name })
  }

  const handleDeleteProject = (projectId: string, projectName: string) => {
    if (!canDeleteWorkspaceResources) return
    setDeleteConfirm({ type: "project", id: projectId, projectId, name: projectName })
  }

  const confirmDelete = async () => {
    if (!deleteConfirm) return
    const { type, id, projectId } = deleteConfirm
    setDeleteConfirm(null)

    try {
      if (type === "project") {
        await workspaceShell.handleDeleteProject(id)
      } else {
        await workspaceShell.handleDeleteConversation(id, projectId)
      }
    } catch {
      // Error already handled by the hook
    }
  }

  return (
    <aside
      className="flex h-full min-h-0 w-full flex-col overflow-hidden border-r border-sidebar-border bg-sidebar text-sidebar-foreground"
      aria-label="Project navigation"
    >
      {/* Header: Logo + Toggle */}
      <div className={cn(
        "flex h-11 shrink-0 items-center",
        collapsed ? "justify-center px-2" : "justify-between px-4"
      )}>
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onCollapsedChange?.(false)}
                className="group relative h-8 w-8 rounded-[8px] text-sidebar-foreground/82 transition-colors hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground focus-visible:bg-sidebar-foreground/[0.06]"
                aria-label={tSidebar("openSidebar")}
              >
                <Logo
                  size={21}
                  className="absolute inset-0 flex items-center justify-center transition-opacity duration-150 group-hover:opacity-0 group-focus-visible:opacity-0"
                />
                <PanelLeftOpen className="h-4 w-4 opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right" sideOffset={12}>{tSidebar("openSidebar")}</TooltipContent>
          </Tooltip>
        ) : (
          <>
            <Link
              href="/agent"
              aria-label="Bioinfoflow"
              className="flex min-w-0 items-center gap-2.5 overflow-hidden rounded-[8px]"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-[8px] text-sidebar-foreground transition-colors duration-200 hover:bg-sidebar-foreground/[0.055]">
                <Logo size={19} className="text-sidebar-foreground" />
              </div>
              <span className="truncate text-[14px] font-semibold text-sidebar-foreground">
                Bioinfoflow
              </span>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onCollapsedChange?.(true)}
              className="h-8 w-8 shrink-0 rounded-[8px] text-sidebar-foreground/68 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
              aria-label={tSidebar("closeSidebar")}
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          </>
        )}
      </div>

      {/* New Conversation CTA */}
      <div className={cn("px-2.5 pb-1.5", collapsed ? "space-y-1 px-2 pt-1" : "pt-1.5")}>
        {collapsed ? (
          <>
            <RailButton
              label={tSidebar("newConversation")}
              onClick={handleNewConversation}
              icon={<SquarePen className="h-3.5 w-3.5" />}
            />
            <RailButton
              label={tSidebar("search")}
              onClick={onCommandOpen}
              icon={<Search className="h-3.5 w-3.5" />}
            />
          </>
        ) : (
          <div className="space-y-1">
            <Button
              className="h-[30px] w-full justify-start gap-2 rounded-[7px] border border-transparent bg-sidebar-foreground/[0.08] px-2.5 text-[12px] font-medium text-sidebar-foreground shadow-none transition-colors duration-200 hover:bg-sidebar-foreground/[0.1]"
              onClick={handleNewConversation}
            >
              <SquarePen className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{tSidebar("newConversation")}</span>
            </Button>
            <Button
              variant="ghost"
              className="h-[30px] w-full justify-start gap-2 rounded-[7px] px-2.5 text-[12px] font-medium text-sidebar-foreground/74 transition-colors hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
              onClick={onCommandOpen}
            >
              <Search className="h-3.5 w-3.5 shrink-0" />
              <span className="truncate">{tSidebar("search")}</span>
            </Button>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className={cn("px-2.5 py-0.5", collapsed && "px-2")}>
        <SidebarNav collapsed={collapsed} />
      </div>

      {!collapsed ? (
        <div className="px-2.5 pb-1 pt-3">
          <div className="group/workspace flex h-7 items-center justify-between gap-1 rounded-[7px] px-1">
            <button
              type="button"
              className="flex min-w-0 flex-1 items-center gap-1.5 text-[12px] font-medium text-sidebar-foreground/62 transition-colors hover:text-sidebar-foreground/82"
              onClick={() => setWorkspaceExpanded((expanded) => !expanded)}
              aria-expanded={workspaceExpanded}
              aria-controls="sidebar-workspace-tree"
            >
              <ChevronRight
                className={cn(
                  "h-3 w-3 shrink-0 transition-transform duration-150",
                  workspaceExpanded && "rotate-90",
                )}
              />
              <span className="truncate">{tSidebar("workspace")}</span>
            </button>
            <div className="flex shrink-0 items-center gap-0.5 text-sidebar-foreground/54 opacity-80 transition-opacity group-hover/workspace:opacity-100">
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-[6px] text-sidebar-foreground/58 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
                onClick={onCommandOpen}
                aria-label={tSidebar("search")}
              >
                <Search className="h-3.5 w-3.5" />
              </Button>
              <Button
                variant="ghost"
                size="icon"
                className="h-6 w-6 rounded-[6px] text-sidebar-foreground/58 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground"
                onClick={workspaceShell.openCreateProjectDialog}
                aria-label={tSidebar("newProject")}
              >
                <Plus className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>
        </div>
      ) : (
        <div className="px-4 py-1.5">
          <div className="border-t border-border/35" />
        </div>
      )}

      {/* Workspace */}
      <div
        id="sidebar-workspace-tree"
        className={cn("min-h-0 flex-1 overflow-y-auto px-2.5 pb-1.5 pt-0.5", collapsed && "px-2")}
      >
        {collapsed || workspaceExpanded ? (
          <ProjectList
            projects={workspaceShell.projects}
            inboxConversations={workspaceShell.inboxConversations}
            defaultProjectId={workspaceShell.defaultProject?.id}
            expandedProjects={workspaceShell.expandedProjects}
            projectConversations={workspaceShell.projectConversations}
            loadingProjects={workspaceShell.loadingProjects}
            collapsed={collapsed}
            activeProjectId={activeProjectId}
            activeConversationId={activeConversationId}
            onToggleExpand={workspaceShell.toggleProjectExpanded}
            onSelectProject={workspaceShell.handleSelectProject}
            onSelectConversation={workspaceShell.handleSelectConversation}
            onMoveConversation={workspaceShell.handleMoveConversation}
            onCreateConversation={workspaceShell.handleCreateConversation}
            onRenameConversation={workspaceShell.handleRenameConversation}
            onDeleteConversation={handleDeleteConversation}
            onRenameProject={workspaceShell.handleRenameProject}
            onDuplicateProject={workspaceShell.handleDuplicateProject}
            onDeleteProject={handleDeleteProject}
            canDeleteWorkspaceResources={canDeleteWorkspaceResources}
            onOpenCreateDialog={workspaceShell.openCreateProjectDialog}
            tSidebar={tSidebar}
            tCommon={tCommon}
          />
        ) : null}

        <CreateProjectDialog
          collapsed={collapsed}
          onCreateProject={workspaceShell.handleCreateProject}
          externalOpen={workspaceShell.createProjectDialogOpen}
          onExternalOpenChange={workspaceShell.setCreateProjectDialogOpen}
          hideTrigger
        />
      </div>

      {/* Bottom Section: Settings + User Menu */}
      <div className={cn("shrink-0 border-t border-sidebar-border/60 bg-sidebar", collapsed ? "px-2 py-2.5" : "px-2.5 py-2.5")}>
        <UserMenu collapsed={collapsed} viewer={viewer} />
      </div>

      <DeleteConfirmDialog
        deleteConfirm={deleteConfirm}
        onCancel={() => setDeleteConfirm(null)}
        onConfirm={confirmDelete}
        tSidebar={tSidebar}
        tCommon={tCommon}
      />
    </aside>
  )
}

function RailButton({
  label,
  icon,
  onClick,
  active,
}: {
  label: string
  icon: ReactNode
  onClick?: () => void
  active?: boolean
}) {
  return (
    <Tooltip>
      <TooltipTrigger asChild>
        <button
          type="button"
          onClick={onClick}
          className={cn(
            "flex h-8 w-full items-center justify-center rounded-[7px] text-sidebar-foreground transition-colors",
            active
              ? "bg-sidebar-foreground/[0.08] text-sidebar-foreground"
              : "text-sidebar-foreground/76 hover:bg-sidebar-foreground/[0.055] hover:text-sidebar-foreground",
          )}
          aria-label={label}
        >
          {icon}
        </button>
      </TooltipTrigger>
      <TooltipContent side="right" sideOffset={12}>{label}</TooltipContent>
    </Tooltip>
  )
}
