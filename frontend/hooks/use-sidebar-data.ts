"use client"

import { useCallback, useEffect, useRef, useState } from "react"
import { useRouter } from "next/navigation"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import type { AgentConversationHistory, AgentConversationRead, Project } from "@/lib/types"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import {
  clearStoredConversationId,
  getStoredConversationId,
  listenForConversationUpdates,
  setStoredConversationId,
  sortConversations,
} from "@/lib/conversations"

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
  const [projectConversations, setProjectConversations] = useState<Map<string, AgentConversationRead[]>>(new Map())
  const [loadingProjects, setLoadingProjects] = useState<Set<string>>(new Set())
  const [defaultProject, setDefaultProject] = useState<Project | null>(null)
  const [inboxConversations, setInboxConversations] = useState<AgentConversationRead[]>([])
  const draftConversationIdsRef = useRef(new Set<string>())

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
      const { data } = await apiRequest<AgentConversationRead[]>("/agent/conversations", {
        params: { project_id: projectId, limit: 50 },
      })
      const sorted = sortConversations(data)
      setProjectConversations((prev) => new Map(prev).set(projectId, sorted))

      if (projectId === selectedProjectId || projectId === conversationProjectId) {
        const storedId = getStoredConversationId(projectId)
        const preferredId = activeConversationId || storedId
        const match = data.find((item) => item.id === preferredId)
        if (match) {
          setActiveConversationId(match.id)
          if (match.id !== storedId) {
            setStoredConversationId(projectId, match.id)
          }
        } else if (data[0]) {
          setActiveConversationId(data[0].id)
          setStoredConversationId(projectId, data[0].id)
        } else {
          setActiveConversationId("")
          clearStoredConversationId(projectId)
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
    return listenForConversationUpdates((conversation) => {
      if (conversation.title?.trim()) {
        draftConversationIdsRef.current.delete(conversation.id)
      }

      setProjectConversations((prev) => {
        const existing = prev.get(conversation.project_id)
        if (!existing) return prev

        const next = existing.map((item) =>
          item.id === conversation.id ? { ...item, ...conversation } : item
        )

        return new Map(prev).set(conversation.project_id, sortConversations(next))
      })
    })
  }, [])

  const discardActiveDraftConversation = useCallback(async () => {
    if (!activeConversationId) return

    const projectId = conversationProjectId || selectedProjectId
    if (!projectId) return

    const conversations = projectConversations.get(projectId) || []
    const conversation = conversations.find((item) => item.id === activeConversationId)
    if (!conversation || conversation.title?.trim()) {
      draftConversationIdsRef.current.delete(activeConversationId)
      return
    }

    const draftId = activeConversationId
    let shouldDiscard = draftConversationIdsRef.current.has(draftId)
    if (!shouldDiscard) {
      try {
        const { data } = await apiRequest<AgentConversationHistory>(
          `/agent/conversations/${draftId}`,
        )
        shouldDiscard = data.messages.length === 0
      } catch {
        return
      }
    }
    if (!shouldDiscard) return

    draftConversationIdsRef.current.delete(draftId)
    try {
      await apiRequest(`/agent/conversations/${draftId}`, { method: "DELETE" })
    } catch {
      return
    }

    setProjectConversations((prev) => {
      const existing = prev.get(projectId) || []
      return new Map(prev).set(projectId, existing.filter((item) => item.id !== draftId))
    })
    if (activeConversationId === draftId) {
      clearStoredConversationId(projectId)
      setActiveConversationId("")
      if (conversationProjectId === projectId) {
        setConversationProjectId("")
      }
    }
  }, [
    activeConversationId,
    conversationProjectId,
    projectConversations,
    selectedProjectId,
    setActiveConversationId,
    setConversationProjectId,
  ])

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
    setSelectedProjectId(project.id)
    setConversationProjectId(project.id)
    setActiveConversationId("")
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
      setSelectedProjectId(data.id)
      setConversationProjectId(data.id)
      setActiveConversationId("")
      toast.success(tSidebar("toasts.projectCreated", { name: data.name }))
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

  const handleSelectConversation = (conversation: AgentConversationRead, projectId: string) => {
    if (defaultProject?.id === projectId) {
      setSelectedProjectId("")
    } else {
      setSelectedProjectId(projectId)
    }
    setConversationProjectId(projectId)
    setActiveConversationId(conversation.id)
    setStoredConversationId(projectId, conversation.id)
    router.push("/agent")
  }

  const handleCreateConversation = async (projectId?: string) => {
    try {
      await discardActiveDraftConversation()
      const targetId = projectId || selectedProjectId
      const { data } = await apiRequest<AgentConversationRead>("/agent/conversations", {
        method: "POST",
        body: JSON.stringify(targetId ? { project_id: targetId } : {}),
      })

      const resolvedProjectId = data.project_id
      setProjectConversations((prev) => {
        const existing = prev.get(resolvedProjectId) || []
        return new Map(prev).set(resolvedProjectId, [data, ...existing])
      })

      if (defaultProject?.id === resolvedProjectId) {
        setSelectedProjectId("")
      } else {
        setSelectedProjectId(resolvedProjectId)
      }
      setConversationProjectId(resolvedProjectId)
      setActiveConversationId(data.id)
      draftConversationIdsRef.current.add(data.id)
      setStoredConversationId(resolvedProjectId, data.id)
      router.push("/agent")
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.createConversationFailed")))
    }
  }

  const handleRenameConversation = async (conversation: AgentConversationRead, projectId: string, newTitle: string) => {
    const trimmed = newTitle.trim()
    if (!trimmed || trimmed === conversation.title) return

    try {
      const { data } = await apiRequest<AgentConversationRead>(
        `/agent/conversations/${conversation.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ title: trimmed }),
        }
      )
      setProjectConversations((prev) => {
        const existing = prev.get(projectId) || []
        return new Map(prev).set(projectId, existing.map((item) => (item.id === conversation.id ? data : item)))
      })
      toast.success(tSidebar("toasts.conversationRenamed"))
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.renameConversationFailed")))
    }
  }

  const handleTogglePin = async (conversation: AgentConversationRead, projectId: string) => {
    try {
      const { data } = await apiRequest<AgentConversationRead>(
        `/agent/conversations/${conversation.id}`,
        {
          method: "PATCH",
          body: JSON.stringify({ pinned: !conversation.pinned }),
        }
      )
      setProjectConversations((prev) => {
        const existing = prev.get(projectId) || []
        return new Map(prev).set(projectId, existing.map((item) => (item.id === conversation.id ? data : item)))
      })
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.updateConversationFailed")))
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
      setSelectedProjectId(created.id)
      setConversationProjectId(created.id)
      setActiveConversationId("")
      toast.success(tSidebar("toasts.projectCreated", { name: created.name }))
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.createProjectFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleDeleteConversation = async (conversationId: string, projectId: string) => {
    try {
      await apiRequest(`/agent/conversations/${conversationId}`, { method: "DELETE" })
      setProjectConversations((prev) => {
        const existing = prev.get(projectId) || []
        return new Map(prev).set(projectId, existing.filter((item) => item.id !== conversationId))
      })
      if (activeConversationId === conversationId) {
        setActiveConversationId("")
        if (conversationProjectId === projectId) {
          setConversationProjectId("")
        }
        clearStoredConversationId(projectId)
      }
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.deleteConversationFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleMoveConversation = async (conversationId: string, fromProjectId: string, targetProjectId: string) => {
    try {
      await apiRequest(`/agent/conversations/${conversationId}/move`, {
        method: "PATCH",
        body: JSON.stringify({ target_project_id: targetProjectId }),
      })
      setProjectConversations((prev) => {
        const next = new Map(prev)
        const fromList = (next.get(fromProjectId) || []).filter((c) => c.id !== conversationId)
        next.set(fromProjectId, fromList)
        return next
      })
      fetchConversationsForProject(targetProjectId)
      if (activeConversationId === conversationId) {
        setSelectedProjectId(targetProjectId)
        setConversationProjectId(targetProjectId)
        setStoredConversationId(targetProjectId, conversationId)
      }
      toast.success(tSidebar("toasts.conversationMoved") || "Conversation moved")
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to move conversation"))
    }
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
    handleTogglePin,
    handleDeleteConversation,
    handleMoveConversation,
  }
}
