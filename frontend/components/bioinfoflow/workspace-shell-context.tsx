"use client"

import { createContext, useContext, useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { useSidebarData } from "@/hooks/use-sidebar-data"

type WorkspaceShellValue = ReturnType<typeof useSidebarData> & {
  createProjectDialogOpen: boolean
  openCreateProjectDialog: () => void
  setCreateProjectDialogOpen: (open: boolean) => void
  navbarActions: React.ReactNode
  setNavbarActions: (actions: React.ReactNode) => void
  hasProjects: boolean
}

const WorkspaceShellContext = createContext<WorkspaceShellValue | null>(null)

export function WorkspaceShellProvider({ children }: { children: React.ReactNode }) {
  const tSidebar = useTranslations("sidebar")
  const sidebarData = useSidebarData(tSidebar)
  const [createProjectDialogOpen, setCreateProjectDialogOpen] = useState(false)
  const [navbarActions, setNavbarActions] = useState<React.ReactNode>(null)

  const value = useMemo<WorkspaceShellValue>(() => ({
    ...sidebarData,
    createProjectDialogOpen,
    openCreateProjectDialog: () => setCreateProjectDialogOpen(true),
    setCreateProjectDialogOpen,
    navbarActions,
    setNavbarActions,
    hasProjects: sidebarData.projects.length > 0,
  }), [sidebarData, createProjectDialogOpen, navbarActions])

  return (
    <WorkspaceShellContext.Provider value={value}>
      {children}
    </WorkspaceShellContext.Provider>
  )
}

export function useOptionalWorkspaceShell() {
  return useContext(WorkspaceShellContext)
}

export function useWorkspaceShell() {
  const context = useOptionalWorkspaceShell()
  if (!context) {
    throw new Error("useWorkspaceShell must be used within WorkspaceShellProvider")
  }
  return context
}
