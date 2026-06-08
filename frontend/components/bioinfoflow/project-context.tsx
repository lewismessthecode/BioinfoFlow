"use client"

import type React from "react"
import { createContext, useContext } from "react"

type ProjectContextValue = {
  selectedProjectId: string
  setSelectedProjectId: (projectId: string) => void
  conversationProjectId: string
  setConversationProjectId: (projectId: string) => void
  activeProjectId: string
  setActiveProjectId: (projectId: string) => void
  selectWorkspaceProject: (projectId: string) => void
  activeConversationId: string
  setActiveConversationId: (conversationId: string) => void
  activeProjectName: string
  setActiveProjectName: (name: string) => void
  activeConversationTitle: string
  setActiveConversationTitle: (title: string) => void
}

const ProjectContext = createContext<ProjectContextValue | null>(null)

export function ProjectProvider({
  value,
  children,
}: {
  value: ProjectContextValue
  children: React.ReactNode
}) {
  return <ProjectContext.Provider value={value}>{children}</ProjectContext.Provider>
}

export function useProjectContext() {
  const context = useContext(ProjectContext)
  if (!context) {
    throw new Error("ProjectContext must be used within ProjectProvider")
  }
  return context
}
