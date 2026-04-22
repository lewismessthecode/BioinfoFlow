"use client"

import { useState } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import Link from "next/link"
import { PanelLeftClose, PanelLeftOpen, SquarePen } from "lucide-react"
import { Button } from "@/components/ui/button"
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { UserMenu } from "@/components/bioinfoflow/user-menu"
import { CreateProjectDialog } from "@/components/bioinfoflow/create-project-dialog"
import { Logo } from "@/components/bioinfoflow/logo"
import { useWorkspaceShell } from "@/components/bioinfoflow/workspace-shell-context"
import type { ViewerIdentity } from "@/lib/auth-config"
import { SidebarNav } from "./sidebar-nav"
import { ProjectList } from "./project-list"
import { DeleteConfirmDialog } from "./delete-confirm-dialog"

interface SidebarProps {
  collapsed: boolean
  onCollapsedChange?: (collapsed: boolean) => void
  viewer?: ViewerIdentity
}

export function Sidebar({ collapsed, onCollapsedChange, viewer }: SidebarProps) {
  const router = useRouter()
  const { activeProjectId, activeConversationId } = useProjectContext()
  const tSidebar = useTranslations("sidebar")
  const tCommon = useTranslations("common")
  const [deleteConfirm, setDeleteConfirm] = useState<{
    type: "project" | "conversation"
    id: string
    projectId: string
    name: string
  } | null>(null)

  const workspaceShell = useWorkspaceShell()

  const canCreateChat = !workspaceShell.isLoading

  const handleNewAnalysis = () => {
    if (canCreateChat) {
      workspaceShell.handleCreateConversation(activeProjectId || undefined)
      return
    }

    router.push("/agent")
  }

  const handleDeleteConversation = (conversationId: string, projectId: string, name: string) => {
    setDeleteConfirm({ type: "conversation", id: conversationId, projectId, name })
  }

  const handleDeleteProject = (projectId: string, projectName: string) => {
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
      className="flex h-full w-full flex-col border-r border-sidebar-border/85 bg-sidebar/96 backdrop-blur-2xl supports-[backdrop-filter]:bg-sidebar/92"
      aria-label="Project navigation"
    >
      {/* Header: Logo + Toggle */}
      <div className={cn(
        "flex shrink-0 items-center border-b border-border/40",
        collapsed ? "h-12" : "h-14",
        collapsed ? "justify-center px-2" : "justify-between px-4"
      )}>
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onCollapsedChange?.(false)}
                className="h-8 w-8 text-sidebar-foreground/78 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground"
              >
                <PanelLeftOpen className="h-4.5 w-4.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">Expand sidebar</TooltipContent>
          </Tooltip>
        ) : (
          <>
            <Link href="/agent" className="flex items-center gap-2.5 overflow-hidden">
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-white/80 text-sidebar-foreground dark:bg-white/5">
                <Logo size={22} className="text-sidebar-foreground" />
              </div>
              <span className="text-base font-bold tracking-tight text-sidebar-foreground whitespace-nowrap">
                Bioinfoflow
              </span>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onCollapsedChange?.(true)}
              className="h-7 w-7 rounded-lg text-sidebar-foreground/72 hover:bg-sidebar-accent/55 hover:text-sidebar-foreground shrink-0"
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          </>
        )}
      </div>

      {/* New Conversation CTA */}
      <div className={cn("px-3 pt-3 pb-2", collapsed && "px-2")}>
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                className="h-10 w-full rounded-[18px] border border-border/85 bg-white/90 text-foreground transition-colors duration-200 hover:bg-white dark:border-border/80 dark:bg-card dark:hover:bg-accent"
                onClick={handleNewAnalysis}
              >
                <SquarePen className="h-4.5 w-4.5" />
              </Button>
            </TooltipTrigger>
            <TooltipContent side="right">{tSidebar("newAnalysis")}</TooltipContent>
          </Tooltip>
        ) : (
          <Button
            className="h-11 w-full justify-start gap-3 rounded-[18px] border border-border/85 bg-white/90 px-3.5 text-sm font-semibold text-foreground transition-colors duration-200 hover:bg-white dark:border-border/80 dark:bg-card dark:hover:bg-accent"
            onClick={handleNewAnalysis}
          >
            <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-xl bg-secondary/75 text-foreground/72">
              <SquarePen className="h-4 w-4 shrink-0" />
            </span>
            <span className="truncate">{tSidebar("newAnalysis")}</span>
          </Button>
        )}
      </div>

      {/* Navigation */}
      <div className={cn("px-3 py-2", collapsed && "px-2")}>
        <SidebarNav collapsed={collapsed} />
      </div>

      {/* Divider + Section Label */}
      {!collapsed && (
        <div className="px-3 pb-1 pt-2">
          <div className="border-t border-border/30" />
          <span className="mt-2 block px-1 text-[10px] font-semibold uppercase tracking-[0.18em] text-sidebar-foreground/45">
            {tSidebar("workspace")}
          </span>
        </div>
      )}
      {collapsed && (
        <div className="px-2 py-1">
          <div className="border-t border-border/30" />
        </div>
      )}

      {/* Workspace */}
      <div className={cn("flex-1 overflow-y-auto px-3 pb-3 pt-1", collapsed && "px-2")}>
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
          onTogglePin={workspaceShell.handleTogglePin}
          onDeleteConversation={handleDeleteConversation}
          onRenameProject={workspaceShell.handleRenameProject}
          onDuplicateProject={workspaceShell.handleDuplicateProject}
          onDeleteProject={handleDeleteProject}
          onOpenCreateDialog={workspaceShell.openCreateProjectDialog}
          tSidebar={tSidebar}
          tCommon={tCommon}
        />

        <CreateProjectDialog
          collapsed={collapsed}
          onCreateProject={workspaceShell.handleCreateProject}
          externalOpen={workspaceShell.createProjectDialogOpen}
          onExternalOpenChange={workspaceShell.setCreateProjectDialogOpen}
          hideTrigger
        />
      </div>

      {/* Bottom Section: Settings + User Menu */}
      <div className={cn("mt-auto border-t border-border/30", collapsed ? "px-2 py-2" : "px-3 py-3")}>
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
