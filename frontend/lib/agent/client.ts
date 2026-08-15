import { apiRequest } from "@/lib/api"

import type {
  AgentCommand,
  AgentPermissionMode,
  AgentSessionStatus,
  AgentWorkspaceAccess,
  SessionSnapshot,
} from "./contracts"

export type AgentSessionSummary = {
  id: string
  title: string | null
  project_id: string | null
  permission_mode: AgentPermissionMode
  workspace_access: AgentWorkspaceAccess
  status: AgentSessionStatus
  created_at: string
  updated_at: string
}

export async function listAgentSessions(options?: {
  includeArchived?: boolean
}) {
  const response = await apiRequest<AgentSessionSummary[]>("/agent/sessions", {
    params: options?.includeArchived ? { include_archived: true } : undefined,
  })
  return response.data
}

export async function createAgentSession(input: {
  projectId?: string | null
  title?: string
  permissionMode?: AgentPermissionMode
  workspaceAccess?: AgentWorkspaceAccess
  modelId?: string
}) {
  const response = await apiRequest<SessionSnapshot>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId ?? null,
      title: input.title,
      permission_mode: input.permissionMode,
      workspace_access: input.workspaceAccess,
      model_id: input.modelId,
    }),
  })
  return response.data
}

export async function getAgentSnapshot(sessionId: string) {
  const response = await apiRequest<SessionSnapshot>(
    `/agent/sessions/${sessionId}/snapshot`,
  )
  return response.data
}

export async function updateAgentSession(
  sessionId: string,
  updates: {
    title?: string | null
    permissionMode?: AgentPermissionMode
    workspaceAccess?: AgentWorkspaceAccess
    status?: Extract<AgentSessionStatus, "active" | "archived">
  },
) {
  const response = await apiRequest<SessionSnapshot>(
    `/agent/sessions/${sessionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        title: updates.title,
        permission_mode: updates.permissionMode,
        workspace_access: updates.workspaceAccess,
        status: updates.status,
      }),
    },
  )
  return response.data
}

export async function dispatchAgentCommand(
  sessionId: string,
  command: AgentCommand,
) {
  const response = await apiRequest<SessionSnapshot>(
    `/agent/sessions/${sessionId}/commands`,
    { method: "POST", body: JSON.stringify(command) },
  )
  return response.data
}

export async function deleteAgentSession(sessionId: string) {
  await apiRequest(`/agent/sessions/${sessionId}`, { method: "DELETE" })
}
