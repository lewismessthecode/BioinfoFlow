import type {
  AgentCoreSession,
  AgentPermissionMode,
} from "@/lib/agent-core/types"

const sessionStorageKey = (projectId: string) => `bioinfoflow:agent-core-session:${projectId}`
const draftPermissionModeKey = (projectId: string) =>
  `bioinfoflow:agent-core-draft-permission-mode:${projectId}`
const draftModelProfileIdKey = (projectId: string) =>
  `bioinfoflow:agent-core-draft-model-profile:${projectId}`
const sessionUpdatedEvent = "bioinfoflow:agent-core-session-updated"

const permissionModes = new Set<AgentPermissionMode>([
  "ask_each_action",
  "guarded_auto",
  "bypass",
])

export type AgentCoreSessionUpdateDetail = Pick<
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

export const getStoredDraftPermissionMode = (
  projectId: string,
): AgentPermissionMode | null => {
  if (typeof window === "undefined") return null
  const value = window.localStorage.getItem(draftPermissionModeKey(projectId))
  return permissionModes.has(value as AgentPermissionMode)
    ? (value as AgentPermissionMode)
    : null
}

export const setStoredDraftPermissionMode = (
  projectId: string,
  mode: AgentPermissionMode,
) => {
  if (typeof window === "undefined") return
  window.localStorage.setItem(draftPermissionModeKey(projectId), mode)
}

export const getStoredDraftModelProfileId = (projectId: string) => {
  if (typeof window === "undefined") return null
  return window.localStorage.getItem(draftModelProfileIdKey(projectId))
}

export const setStoredDraftModelProfileId = (
  projectId: string,
  profileId: string | null,
) => {
  if (typeof window === "undefined") return
  if (profileId) {
    window.localStorage.setItem(draftModelProfileIdKey(projectId), profileId)
  } else {
    window.localStorage.removeItem(draftModelProfileIdKey(projectId))
  }
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
