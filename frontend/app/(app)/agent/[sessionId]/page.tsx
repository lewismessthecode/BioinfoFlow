"use client"

import { useEffect, useMemo, useState } from "react"
import { useParams } from "next/navigation"

import { AgentPageContent } from "../page"
import { useProjectContext } from "@/components/bioinfoflow/project-context"
import { apiRequest } from "@/lib/api"
import { setStoredAgentSessionId } from "@/lib/agent-core/session-storage"
import { getAgentRuntimeSession } from "@/lib/agent-runtime/client"
import type { Project } from "@/lib/types"

type RouteProjectContext = {
  sessionId: string
  selectedProjectId: string
  conversationProjectId: string
}

export default function AgentSessionPage() {
  const params = useParams<{ sessionId: string }>()
  const sessionId = useMemo(() => {
    const value = params.sessionId
    return Array.isArray(value) ? value[0] : value
  }, [params.sessionId])

  return <ResolvedAgentSessionPage key={sessionId} sessionId={sessionId} />
}

function ResolvedAgentSessionPage({ sessionId }: { sessionId: string }) {
  const {
    selectedProjectId,
    setSelectedProjectId,
    conversationProjectId,
    setConversationProjectId,
    activeConversationId,
    setActiveConversationId,
  } = useProjectContext()
  const [routeProjectContext, setRouteProjectContext] =
    useState<RouteProjectContext | null>(() =>
      activeConversationId === sessionId && conversationProjectId
        ? { sessionId, selectedProjectId, conversationProjectId }
        : null,
    )

  useEffect(() => {
    setActiveConversationId(sessionId)
    let cancelled = false

    void Promise.all([
      getAgentRuntimeSession(sessionId),
      apiRequest<Project>("/projects/default").catch(() => null),
    ])
      .then(([session, defaultProjectResponse]) => {
        if (cancelled) return
        const projectId = session.project_id ?? ""
        const defaultProjectId = defaultProjectResponse?.data?.id ?? null
        const selectedProject = projectId && projectId !== defaultProjectId ? projectId : ""
        setSelectedProjectId(selectedProject)
        setConversationProjectId(projectId)
        setActiveConversationId(session.id)
        setRouteProjectContext({
          sessionId,
          selectedProjectId: selectedProject,
          conversationProjectId: projectId,
        })
        if (projectId) {
          setStoredAgentSessionId(projectId, session.id)
        }
      })
      .catch(() => {
        if (!cancelled) {
          setRouteProjectContext({
            sessionId,
            selectedProjectId: "",
            conversationProjectId: "",
          })
        }
      })

    return () => {
      cancelled = true
    }
  }, [
    sessionId,
    setActiveConversationId,
    setConversationProjectId,
    setSelectedProjectId,
  ])

  const isResolvingSession = routeProjectContext?.sessionId !== sessionId
  if (isResolvingSession) return null

  const pageProjectId =
    routeProjectContext?.conversationProjectId ?? conversationProjectId
  const pageSelectedProjectId =
    routeProjectContext?.selectedProjectId ?? selectedProjectId

  return (
    <AgentPageContent
      key={`${pageSelectedProjectId || "no-selected"}:${pageProjectId || "no-conversation-project"}:${sessionId}`}
      selectedProjectId={pageSelectedProjectId}
      conversationProjectId={pageProjectId}
      activeConversationId={sessionId}
    />
  )
}
