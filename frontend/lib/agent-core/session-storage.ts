import type {
  AgentCoreSession,
} from "@/lib/agent-core/types"

const sessionStorageKey = (projectId: string) => `bioinfoflow:agent-core-session:${projectId}`
const sessionUpdatedEvent = "bioinfoflow:agent-core-session-updated"

type AgentCoreSessionUpdateDetail = Pick<
  AgentCoreSession,
  "id" | "project_id" | "title" | "created_at" | "updated_at"
>

export const getStoredAgentSessionId = (projectId: string) => {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(sessionStorageKey(projectId))
}

export const setStoredAgentSessionId = (projectId: string, sessionId: string) => {
  if (typeof window === "undefined") return
  window.localStorage.setItem(sessionStorageKey(projectId), sessionId)
}

export const clearStoredAgentSessionId = (projectId: string) => {
  if (typeof window === "undefined") return
  window.localStorage.removeItem(sessionStorageKey(projectId))
}

export const emitAgentSessionUpdated = (session: AgentCoreSessionUpdateDetail) => {
  if (typeof window === "undefined") return
  window.dispatchEvent(
    new CustomEvent<AgentCoreSessionUpdateDetail>(sessionUpdatedEvent, {
      detail: session,
    }),
  )
}

export const listenForAgentSessionUpdates = (
  listener: (session: AgentCoreSessionUpdateDetail) => void,
) => {
  if (typeof window === "undefined") return () => {}

  const handleEvent = (event: Event) => {
    const customEvent = event as CustomEvent<AgentCoreSessionUpdateDetail>
    if (!customEvent.detail) return
    listener(customEvent.detail)
  }

  window.addEventListener(sessionUpdatedEvent, handleEvent as EventListener)
  return () => {
    window.removeEventListener(sessionUpdatedEvent, handleEvent as EventListener)
  }
}

export const sortAgentSessions = (sessions: AgentCoreSession[]): AgentCoreSession[] =>
  [...sessions].sort(
    (a, b) =>
      new Date(b.updated_at || b.created_at || 0).getTime() -
      new Date(a.updated_at || a.created_at || 0).getTime(),
  )
