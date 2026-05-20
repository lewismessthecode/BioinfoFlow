"use client"

import { useState, type ReactNode } from "react"
import { useRouter } from "next/navigation"
import { useTranslations } from "next-intl"
import { cn } from "@/lib/utils"
import Link from "next/link"
import { PanelLeftClose, PanelLeftOpen, Search, SquarePen } from "lucide-react"
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
  onCommandOpen?: () => void
  runtimeMode?: unknown
  viewer?: ViewerIdentity
}

export function Sidebar({ collapsed, onCollapsedChange, onCommandOpen, viewer }: SidebarProps) {
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
      className="flex h-full w-full flex-col border-r border-sidebar-border/80 bg-sidebar/96 backdrop-blur-2xl supports-[backdrop-filter]:bg-sidebar/90"
      aria-label="Project navigation"
    >
      {/* Header: Logo + Toggle */}
      <div className={cn(
        "flex shrink-0 items-center",
        collapsed ? "h-[58px] justify-center px-2 pt-2" : "h-[60px] justify-between px-5"
      )}>
        {collapsed ? (
          <Tooltip>
            <TooltipTrigger asChild>
              <Button
                variant="ghost"
                size="icon"
                onClick={() => onCollapsedChange?.(false)}
                className="group relative h-9 w-9 rounded-full text-sidebar-foreground/86 transition-colors hover:bg-sidebar-accent hover:text-sidebar-foreground focus-visible:bg-sidebar-accent"
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
              className="flex min-w-0 items-center gap-3 overflow-hidden rounded-2xl"
            >
              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-sidebar-foreground transition-colors duration-200 hover:bg-sidebar-accent/75">
                <Logo size={21} className="text-sidebar-foreground" />
              </div>
              <span className="truncate text-[15px] font-semibold tracking-tight text-sidebar-foreground">
                Bioinfoflow
              </span>
            </Link>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => onCollapsedChange?.(true)}
              className="h-[34px] w-[34px] rounded-full text-sidebar-foreground/72 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground shrink-0"
              aria-label={tSidebar("closeSidebar")}
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          </>
        )}
      </div>

      {/* New Conversation CTA */}
      <div className={cn("px-3 pb-2", collapsed ? "space-y-1.5 px-2 pt-1.5" : "pt-2")}>
        {collapsed ? (
          <>
            <RailButton
              label={tSidebar("newAnalysis")}
              onClick={handleNewAnalysis}
              active
              icon={<SquarePen className="h-4 w-4" />}
            />
            <RailButton
              label={tSidebar("search")}
              onClick={onCommandOpen}
              icon={<Search className="h-4 w-4" />}
            />
          </>
        ) : (
          <div className="space-y-1">
            <Button
              className="h-[38px] w-full justify-start gap-3 rounded-full border border-transparent bg-sidebar-accent px-4 text-[13px] font-semibold text-foreground shadow-none transition-colors duration-200 hover:bg-sidebar-accent/80"
              onClick={handleNewAnalysis}
            >
              <SquarePen className="h-4 w-4 shrink-0" />
              <span className="truncate">{tSidebar("newAnalysis")}</span>
            </Button>
            <Button
              variant="ghost"
              className="h-[34px] w-full justify-start gap-3 rounded-full px-4 text-[13px] font-medium text-sidebar-foreground/82 transition-colors hover:bg-sidebar-accent/65 hover:text-sidebar-foreground"
              onClick={onCommandOpen}
            >
              <Search className="h-4 w-4 shrink-0" />
              <span className="truncate">{tSidebar("search")}</span>
            </Button>
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className={cn("px-3 py-1", collapsed && "px-2")}>
        <SidebarNav collapsed={collapsed} />
      </div>

      {/* Divider + Section Label */}
      {!collapsed && (
        <div className="px-5 pb-1 pt-5">
          <span className="block px-0 text-[13px] font-medium text-sidebar-foreground/58">
            {tSidebar("workspace")}
          </span>
        </div>
      )}
      {collapsed && (
        <div className="px-4 py-1.5">
          <div className="border-t border-border/35" />
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
      <div className={cn("mt-auto", collapsed ? "px-2 py-3" : "px-4 py-4")}>
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
            "flex h-9 w-full items-center justify-center rounded-full text-sidebar-foreground transition-colors",
            active
              ? "bg-sidebar-accent text-sidebar-foreground"
              : "text-sidebar-foreground/82 hover:bg-sidebar-accent/70 hover:text-sidebar-foreground",
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
