"use client"

import { createContext, useContext, useMemo, useState } from "react"
import { useTranslations } from "next-intl"
import { useSidebarData } from "@/hooks/use-sidebar-data"

type WorkspaceShellValue = ReturnType<typeof useSidebarData> & {
  createProjectDialogOpen: boolean
  openCreateProjectDialog: () => void
  setCreateProjectDialogOpen: (open: boolean) => void
  hasProjects: boolean
}

const WorkspaceShellContext = createContext<WorkspaceShellValue | null>(null)

export function WorkspaceShellProvider({ children }: { children: React.ReactNode }) {
  const tSidebar = useTranslations("sidebar")
  const sidebarData = useSidebarData(tSidebar)
  const [createProjectDialogOpen, setCreateProjectDialogOpen] = useState(false)

  const value = useMemo<WorkspaceShellValue>(() => ({
    ...sidebarData,
    createProjectDialogOpen,
    openCreateProjectDialog: () => setCreateProjectDialogOpen(true),
    setCreateProjectDialogOpen,
    hasProjects: sidebarData.projects.length > 0,
  }), [sidebarData, createProjectDialogOpen])

  return (
    <WorkspaceShellContext.Provider value={value}>
      {children}
    </WorkspaceShellContext.Provider>
  )
}

export function useWorkspaceShell() {
  const context = useContext(WorkspaceShellContext)
  if (!context) {
    throw new Error("useWorkspaceShell must be used within WorkspaceShellProvider")
  }
  return context
}
