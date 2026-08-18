"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import { usePathname, useRouter } from "next/navigation"
import { toast } from "sonner"
import { apiRequest, getApiErrorMessage } from "@/lib/api"
import {
  deleteAgentSession,
  listAgentSessions,
  updateAgentSession,
  type AgentSessionSummary,
} from "@/lib/agent/client"
import type { Project } from "@/lib/types"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import {
  sessionSummaryFromView,
  sortAgentSessionSummaries,
  subscribeAgentSessionSummaries,
} from "@/lib/agent/session-preferences"
import { celebrateMilestone } from "@/lib/celebrations"
import { useFirstRunLoadingContext } from "@/hooks/use-first-run"

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
  const firstRunLoading = useFirstRunLoadingContext()
  const {
    selectedProjectId,
    setSelectedProjectId,
    conversationProjectId,
    setConversationProjectId,
    activeConversationId,
    setActiveConversationId,
    selectWorkspaceProject,
    setActiveProjectName,
    setActiveConversationTitle,
  } = useProjectContext()
  const router = useRouter()
  const pathname = usePathname()

  const [projects, setProjects] = useState<Project[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [expandedProjects, setExpandedProjects] = useState<Set<string>>(new Set())
  const [sessions, setSessions] = useState<AgentSessionSummary[]>([])
  const [defaultProject, setDefaultProject] = useState<Project | null>(null)

  const fetchSidebarData = useCallback(async () => {
    setIsLoading(true)
    try {
      const [projectsResult, defaultResult, sessionSummaries] = await Promise.all([
        apiRequest<Project[]>("/projects", { params: { limit: 100 } }),
        apiRequest<Project>("/projects/default").catch(() => null),
        listAgentSessions(),
      ])
      const allProjects = projectsResult.data
      const defProj = defaultResult?.data ?? null
      const regular = allProjects.filter((p) => !p.is_default)
      const sorted = [...regular].sort((a, b) => a.name.localeCompare(b.name))
      setProjects(sorted)
      setDefaultProject(defProj)
      setSessions(sortAgentSessionSummaries(sessionSummaries))
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to load projects"))
    } finally {
      setIsLoading(false)
    }
  }, [])

  const fetchProjects = useCallback(async () => {
    try {
      const [projectsResult, defaultResult] = await Promise.all([
        apiRequest<Project[]>("/projects", { params: { limit: 100 } }),
        apiRequest<Project>("/projects/default").catch(() => null),
      ])
      setProjects(
        projectsResult.data
          .filter((project) => !project.is_default)
          .sort((left, right) => left.name.localeCompare(right.name)),
      )
      setDefaultProject(defaultResult?.data ?? null)
    } catch (error) {
      toast.error(getApiErrorMessage(error, "Failed to load projects"))
    }
  }, [])

  const projectConversations = useMemo(
    () => groupSessionsByProject(sessions, defaultProject?.id),
    [defaultProject?.id, sessions],
  )
  const loadingProjects = useMemo(() => new Set<string>(), [])
  const inboxConversations = useMemo(
    () => (defaultProject ? projectConversations.get(defaultProject.id) ?? [] : []),
    [defaultProject, projectConversations],
  )

  useEffect(() => {
    if (firstRunLoading) return
    fetchSidebarData()
  }, [fetchSidebarData, firstRunLoading])

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
    const onAgentRoute = pathname === "/agent" || pathname.startsWith("/agent/")
    if (!onAgentRoute) return
    if (selectedProjectId || conversationProjectId) return

    const regularProjects = projects.filter((project) => !project.is_default)
    if (regularProjects.length === 0) return

    const storedProjectId = getStoredLastUsedProjectId()
    const restoredProject =
      regularProjects.find((project) => project.id === storedProjectId) ??
      regularProjects[0]

    if (restoredProject) {
      selectWorkspaceProject(restoredProject.id)
    }
  }, [
    conversationProjectId,
    pathname,
    projects,
    selectWorkspaceProject,
    selectedProjectId,
  ])

  useEffect(() => {
    if (!selectedProjectId) return

    setExpandedProjects((prev) => {
      if (prev.has(selectedProjectId)) return prev
      return new Set(prev).add(selectedProjectId)
    })
  }, [selectedProjectId])

  useEffect(() => {
    const onAgentRoute = pathname === "/agent" || pathname.startsWith("/agent/")
    if (!onAgentRoute) return
    if (!defaultProject) return
    if (projects.some((project) => !project.is_default)) return
    if (selectedProjectId || conversationProjectId) return
    const timer = window.setTimeout(() => {
      setConversationProjectId(defaultProject.id)
      setActiveConversationId("")
    }, 0)
    return () => window.clearTimeout(timer)
  }, [
    conversationProjectId,
    defaultProject,
    pathname,
    projects,
    selectedProjectId,
    setActiveConversationId,
    setConversationProjectId,
  ])

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
    return subscribeAgentSessionSummaries((update) => {
      setSessions((current) => {
        if (update.kind === "conversation") {
          const summary = update.summary
          if (!current.some((item) => item.id === summary.id)) return current
          return current.map((item) =>
            item.id === summary.id
              ? {
                  ...item,
                  title: summary.title,
                  project_id: summary.projectId,
                  status: summary.status,
                }
              : item,
          )
        }

        const summary = update.summary
        const exists = current.some((item) => item.id === summary.id)
        const next = exists
          ? current.map((item) => (item.id === summary.id ? summary : item))
          : [summary, ...current]
        return sortAgentSessionSummaries(next)
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
      }
      return next
    })
  }

  const handleSelectProject = (project: Project) => {
    selectWorkspaceProject(project.id)
    if (!expandedProjects.has(project.id)) {
      toggleProjectExpanded(project.id)
    }
  }

  const handleCreateProject = async (projectData: {
    name: string
    description: string
    projectType?: "local" | "remote"
    storageOverridePath?: string
    remoteConnectionId?: string
    remoteRootPath?: string
  }) => {
    if (!projectData.name.trim()) {
      const message = tSidebar("errors.projectNameRequired")
      toast.error(message)
      throw new Error(message)
    }

    try {
      const isRemoteProject = projectData.projectType === "remote"
      const { data } = await apiRequest<Project>("/projects", {
        method: "POST",
        body: JSON.stringify({
          name: projectData.name.trim(),
          description: projectData.description.trim() || null,
          ...(isRemoteProject
            ? {
                remote_connection_id: projectData.remoteConnectionId,
                remote_root_path: projectData.remoteRootPath?.trim(),
              }
            : projectData.storageOverridePath?.trim()
              ? { external_root_path: projectData.storageOverridePath.trim() }
              : {}),
        }),
      })

      setProjects((prev) => [data, ...prev])
      selectWorkspaceProject(data.id)
      toast.success(tSidebar("toasts.projectCreated", { name: data.name }))
      celebrateMilestone("first-project")
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
      setSessions((current) =>
        current.filter((session) => session.project_id !== projectId),
      )
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

  const handleSelectConversation = (conversation: AgentSessionSummary, projectId: string) => {
    if (defaultProject?.id === projectId) {
      setSelectedProjectId("")
    } else {
      setSelectedProjectId(projectId)
      setStoredLastUsedProjectId(projectId)
    }
    setConversationProjectId(projectId)
    setActiveConversationId(conversation.id)
    router.push(`/agent/${conversation.id}`)
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
      router.push("/agent")
    } catch (error) {
      toast.error(getApiErrorMessage(error, tSidebar("errors.createConversationFailed")))
    }
  }

  const handleRenameConversation = async (conversation: AgentSessionSummary, projectId: string, newTitle: string) => {
    const trimmed = newTitle.trim()
    if (!trimmed || trimmed === conversation.title) return
    void projectId

    try {
      const snapshot = await updateAgentSession(conversation.id, { title: trimmed })
      setSessions((current) =>
        sortAgentSessionSummaries(
          current.map((item) =>
            item.id === conversation.id ? sessionSummaryFromView(snapshot.session) : item,
          ),
        ),
      )
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
      selectWorkspaceProject(created.id)
      toast.success(tSidebar("toasts.projectCreated", { name: created.name }))
      celebrateMilestone("first-project")
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.createProjectFailed"))
      toast.error(message)
      throw error
    }
  }

  const handleDeleteConversation = async (conversationId: string, projectId: string) => {
    try {
      await deleteAgentSession(conversationId)
      setSessions((current) => current.filter((item) => item.id !== conversationId))
      if (activeConversationId === conversationId) {
        setActiveConversationId("")
        if (conversationProjectId === projectId) {
          setConversationProjectId("")
        }
      }
      if (pathname === `/agent/${conversationId}`) {
        router.replace("/agent")
      }
    } catch (error) {
      const message = getApiErrorMessage(error, tSidebar("errors.deleteConversationFailed"))
      toast.error(message)
      throw error
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
    handleDeleteConversation,
  }
}

function groupSessionsByProject(
  sessions: AgentSessionSummary[],
  defaultProjectId?: string,
) {
  const grouped = new Map<string, AgentSessionSummary[]>()
  for (const session of sessions) {
    const projectId = session.project_id ?? defaultProjectId
    if (!projectId) continue
    grouped.set(projectId, [...(grouped.get(projectId) ?? []), session])
  }
  return grouped
}
