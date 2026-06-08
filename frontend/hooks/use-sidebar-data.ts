"use client"

import { useCallback, useEffect, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import {
  deleteAgentSession,
  listAgentSessions,
  updateAgentSession,
  type AgentCoreSession,
} from "@/lib/agent-core"
import type { Project } from "@/lib/types"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import {
  clearStoredAgentSessionId,
  getStoredAgentSessionId,
  listenForAgentSessionUpdates,
  setStoredAgentSessionId,
  sortAgentSessions,
} from "@/lib/agent-core/session-storage"
import { emitReadinessRefresh } from "@/lib/readiness-events"

const LAST_USED_PROJECT_STORAGE_KEY = "bioinfoflow:last-used-project"

function getStoredLastUsedProjectId(): string {
  return window.localStorage.getItem(LAST_USED_PROJECT_STORAGE_KEY) ?? ""
}

function setStoredLastUsedProjectId(projectId: string | null) {
  if (projectId) {
    window.localStorage.setItem(LAST_USED_PROJECT_STORAGE_KEY, projectId)
    return
  }
  window.localStorage.removeItem(LAST_USED_PROJECT_STORAGE_KEY)
}

export function useSidebarData(tSidebar: (key: string, values?: Record<string, string>) => string) {
  const {
    selectedProjectId,
    setSelectedProjectId,
    conversationProjectId,
    setConversationProjectId,
    activeConversationId,
    setActiveConversationId,
    setActiveProjectName,
    setActiveConversationTitle,
  } = useProjectContext()
  const router = useRouter()

  const [projects, setProjects] = useState<Project[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set())
  const [projectConversations, setProjectConversations] = useState<Map<string, AgentCoreSession[]>>(new Map())
  const [loadingProjects, setLoadingProjects] = useState<Set<string>>(new Set())
  const [defaultProject, setDefaultProject] = useState<Project | null>(null)
  const [inboxConversations, setInboxConversations] = useState<AgentCoreSession[]>([])

  const selectProjectForWorkspace = useCallback((projectId: string) => {
    setSelectedProjectId(projectId)
    setConversationProjectId(projectId)
    setActiveConversationId("")
  }, [setActiveConversationId, setConversationProjectId, setSelectedProjectId])

  const fetchProjects = useCallback(async () => {
    setIsLoading(true)
    try {
      const [projectsResult, defaultResult] = await Promise.all([
        apiRequest<Project[]>("/projects", { params: { limit: 100 } }),
        apiRequest<Project>("/projects/default").catch(() => null),
      ])
      const allProjects = projectsResult.data
      const defProj = defaultResult?.data ?? null
      const regular = allProjects.filter((p) => !p.is_default)
      const sorted = [...regular].sort((a, b) => a.name.localeCompare(b.name))
      setProjects(sorted)
      setDefaultProject(defProj)
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to load projects"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchConversationsForProject = useCallback(async (projectId: string) => {
    setLoadingProjects((prev) => new Set(prev).add(projectId))
    try {
      const data = await listAgentSessions(projectId)
      const sorted = sortAgentSessions(data)
      setProjectConversations((prev) => new Map(prev).set(projectId, sorted))

      if (projectId === selectedProjectId || projectId === conversationProjectId) {
        const storedId = getStoredAgentSessionId(projectId)
        const preferredId = activeConversationId || storedId
        if (preferredId) {
          const match = data.find((item) => item.id === preferredId)
          if (match) {
            setActiveConversationId(match.id)
            if (match.id !== storedId) {
              setStoredAgentSessionId(projectId, match.id)
            }
          } else {
            setActiveConversationId("")
            clearStoredAgentSessionId(projectId)
          }
        } else {
          setActiveConversationId("")
          clearStoredAgentSessionId(projectId)
        }
      }
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to load conversations"))
    } finally {
      setLoadingProjects((prev) => {
        const next = new Set(prev)
        next.delete(projectId)
        return next
      })
    }
  }, [selectedProjectId, conversationProjectId, activeConversationId, setActiveConversationId])

  useEffect(() => {
    fetchProjects()
  }, [fetchProjects])

  useEffect(() => {
    if (!selectedProjectId) return
    if (projects.some((project) => project.id === selectedProjectId)) return
    fetchProjects()
  }, [selectedProjectId, projects, fetchProjects])

  useEffect(() => {
    if (!selectedProjectId) {
      return
    }
    const activeProject = projects.find((project) => project.id === selectedProjectId)
    if (activeProject && !activeProject.is_default) {
      setStoredLastUsedProjectId(activeProject.id)
    }
  }, [projects, selectedProjectId])

  useEffect(() => {
    if (!selectedProjectId) return

    setExpandedProjects((prev) => {
      if (prev.has(selectedProjectId)) return prev
      return new Set(prev).add(selectedProjectId)
    })

    if (!projectConversations.has(selectedProjectId)) {
      fetchConversationsForProject(selectedProjectId)
    }
  }, [selectedProjectId, projectConversations, fetchConversationsForProject])

  useEffect(() => {
    if (!selectedProjectId || !activeConversationId) return
    const conversations = projectConversations.get(selectedProjectId) || []
    if (conversations.some((item) => item.id === activeConversationId)) return
    fetchConversationsForProject(selectedProjectId)
  }, [activeConversationId, selectedProjectId, projectConversations, fetchConversationsForProject])

  useEffect(() => {
    if (!defaultProject) return
    if (!projectConversations.has(defaultProject.id)) {
      fetchConversationsForProject(defaultProject.id)
    }
  }, [defaultProject, projectConversations, fetchConversationsForProject])

  useEffect(() => {
    const project = projects.find((p) => p.id === selectedProjectId)
    setActiveProjectName(project?.name || "")
  }, [selectedProjectId, projects, setActiveProjectName])

  useEffect(() => {
    const currentProjectId = conversationProjectId || selectedProjectId
    if (!currentProjectId || !activeConversationId) {
      setActiveConversationTitle("")
      return
    }
    const conversations = projectConversations.get(currentProjectId) || []
    const conversation = conversations.find((c) => c.id === activeConversationId)
    setActiveConversationTitle(conversation?.title || "")
  }, [selectedProjectId, conversationProjectId, activeConversationId, projectConversations, setActiveConversationTitle])

  useEffect(() => {
    if (!defaultProject) return
    setInboxConversations(projectConversations.get(defaultProject.id) || [])
  }, [defaultProject, projectConversations])

  useEffect(() => {
    return listenForAgentSessionUpdates((conversation) => {
      setProjectConversations((prev) => {
        const existing = prev.get(conversation.project_id)
        if (!existing) return prev

        const next = existing.map((item) =>
          item.id === conversation.id ? { ...item, ...conversation } : item
        )

        return new Map(prev).set(conversation.project_id, sortAgentSessions(next))
      })
    })
  }, [])

  const toggleProjectExpanded = (projectId: string) => {
    setExpandedProjects((prev) => {
      const next = new Set(prev)
      if (next.has(projectId)) {
        next.delete(projectId)
      } else {
        next.add(projectId)
        if (!projectConversations.has(projectId)) {
          fetchConversationsForProject(projectId)
        }
      }
      return next
    })
  }

  const handleSelectProject = (project: Project) => {
    selectProjectForWorkspace(project.id)
    if (!expandedProjects.has(project.id)) {
      toggleProjectExpanded(project.id)
    }
  }

  const handleCreateProject = async (projectData: {
    name: string
    description: string
    storageOverridePath?: string
  }) => {
    if (!projectData.name.trim()) {
      const message = tSidebar("errors.projectNameRequired")
      toast.error(message)
      throw new Error(message)
    }

    try {
      const { data } = await apiRequest<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: projectData.name.trim(),
          description: projectData.description.trim() || null,
          ...(projectData.storageOverridePath?.trim()
            ? { external_root_path: projectData.storageOverridePath.trim() }
            : {}),
        }),
      })

      setProjects((prev) => [data, ...prev])
      selectProjectForWorkspace(data.id)
      toast.success(tSidebar("toasts.projectCreated", { name: data.name }))
      emitReadinessRefresh("project-created")
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.createProjectFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleRenameProject = async (project: Project, newName: string) => {
    const trimmed = newName.trim()
    if (!trimmed || trimmed === project.name) return

    try {
      const { data } = await apiRequest<Project>(`/projects/${project.id}`, {
        method: "PATCH",
        body: JSON.stringify({ name: trimmed }),
      })
      setProjects((prev) => prev.map((item) => (item.id === project.id ? data : item)))
      toast.success(tSidebar("toasts.projectRenamed", { name: data.name }))
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.renameProjectFailed")))
    }
  }

  const handleDuplicateProject = async (project: Project) => {
    try {
      const { data } = await apiRequest<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: tSidebar("copyOf", { name: project.name }),
          description: project.description,
        }),
      })
      setProjects((prev) => [data, ...prev])
      toast.success(tSidebar("toasts.projectDuplicated", { name: project.name }))
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.duplicateProjectFailed")))
    }
  }

  const handleDeleteProject = async (projectId: string) => {
    try {
      await apiRequest(`/projects/${projectId}`, { method: "DELETE" })
      setProjects((prev) => prev.filter((item) => item.id !== projectId))
      if (getStoredLastUsedProjectId() === projectId) {
        setStoredLastUsedProjectId(null)
      }
      if (selectedProjectId === projectId) {
        setSelectedProjectId("")
      }
      if (conversationProjectId === projectId) {
        setConversationProjectId("")
        setActiveConversationId("")
      }
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.deleteProjectFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleSelectConversation = (conversation: AgentCoreSession, projectId: string) => {
    if (defaultProject?.id === projectId) {
      setSelectedProjectId("")
    } else {
      setSelectedProjectId(projectId)
      setStoredLastUsedProjectId(projectId)
    }
    setConversationProjectId(projectId)
    setActiveConversationId(conversation.id)
    setStoredAgentSessionId(projectId, conversation.id)
    router.push("/agent")
  }

  const handleCreateConversation = async (projectId?: string) => {
    try {
      const targetId = projectId || selectedProjectId || defaultProject?.id
      if (!targetId) {
        toast.error(tSidebar("errors.selectProjectFirst"))
        return
      }

      if (defaultProject?.id === targetId) {
        setSelectedProjectId("")
      } else {
        setSelectedProjectId(targetId)
        setStoredLastUsedProjectId(targetId)
      }
      setConversationProjectId(targetId)
      setActiveConversationId("")
      clearStoredAgentSessionId(targetId)
      router.push("/agent")
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.createConversationFailed")))
    }
  }

  const handleRenameConversation = async (conversation: AgentCoreSession, projectId: string, newTitle: string) => {
    const trimmed = newTitle.trim()
    if (!trimmed || trimmed === conversation.title) return

    try {
      const data = await updateAgentSession(conversation.id, { title: trimmed })
      setProjectConversations((prev) => {
        const existing = prev.get(projectId) || []
        return new Map(prev).set(projectId, existing.map((item) => (item.id === conversation.id ? data : item)))
      })
      toast.success(tSidebar("toasts.conversationRenamed"))
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.renameConversationFailed")))
    }
  }

  const handleQuickCreateProject = async (data: { name: string; description: string }) => {
    try {
      const { data: created } = await apiRequest<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: data.name,
          description: data.description,
        }),
      })

      setProjects((prev) => [created, ...prev])
      selectProjectForWorkspace(created.id)
      toast.success(tSidebar("toasts.projectCreated", { name: created.name }))
      emitReadinessRefresh("project-created")
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.createProjectFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleDeleteConversation = async (conversationId: string, projectId: string) => {
    try {
      await deleteAgentSession(conversationId)
      setProjectConversations((prev) => {
        const existing = prev.get(projectId) || []
        return new Map(prev).set(projectId, existing.filter((item) => item.id !== conversationId))
      })
      if (activeConversationId === conversationId) {
        setActiveConversationId("")
        if (conversationProjectId === projectId) {
          setConversationProjectId("")
        }
        clearStoredAgentSessionId(projectId)
      }
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.deleteConversationFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleMoveConversation = async (conversationId: string, fromProjectId: string, targetProjectId: string) => {
    void conversationId
    void fromProjectId
    void targetProjectId
    toast.error(tSidebar("errors.updateConversationFailed"))
  }

  return {
    projects,
    defaultProject,
    inboxConversations,
    isLoading,
    expandedProjects,
    projectConversations,
    loadingProjects,
    toggleProjectExpanded,
    handleSelectProject,
    handleCreateProject,
    handleQuickCreateProject,
    handleRenameProject,
    handleDuplicateProject,
    handleDeleteProject,
    handleSelectConversation,
    handleCreateConversation,
    handleRenameConversation,
    handleDeleteConversation,
    handleMoveConversation,
  }
}
