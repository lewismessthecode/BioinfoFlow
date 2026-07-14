import { apiRequest } from "@/lib/api"
import type {
  AgentCoreSession,
  AgentPermissionMode,
  AgentAutomationMode,
  AgentModelSelection,
  AgentPendingStrategy,
} from "@/lib/agent-core/types"

type UpdateAgentSessionInput = {
  title?: string
  roleProfile?: string
  permissionMode?: AgentPermissionMode
  automationMode?: AgentAutomationMode
  defaultModelProfileId?: string | null
  modelSelection?: AgentModelSelection | null
  status?: AgentCoreSession["status"]
  metadata?: Record<string, unknown> | null
  pendingStrategy?: AgentPendingStrategy
}

export const listAgentSessions = async (
  projectId?: string,
  options?: { includeChildren?: boolean; parentSessionId?: string },
) => {
  const params: Record<string, string | boolean> = {}
  if (projectId) params.project_id = projectId
  if (options?.parentSessionId) params.parent_session_id = options.parentSessionId
  if (options?.includeChildren) params.include_children = true
  const response = await apiRequest<AgentCoreSession[]>("/agent/sessions", {
    params: Object.keys(params).length ? params : undefined,
  })
  return response.data
}

export const updateAgentSession = async (
  sessionId: string,
  updates: UpdateAgentSessionInput,
) => {
  const response = await apiRequest<AgentCoreSession>(`/agent/sessions/${sessionId}`, {
    method: "PATCH",
    body: JSON.stringify({
      title: updates.title,
      role_profile: updates.roleProfile,
      permission_mode: updates.permissionMode,
      automation_mode: updates.automationMode,
      default_model_profile_id: updates.defaultModelProfileId,
      model_selection: updates.modelSelection,
      status: updates.status,
      metadata: updates.metadata,
      pending_strategy: updates.pendingStrategy,
    }),
  })
  return response.data
}

export const deleteAgentSession = async (sessionId: string) => {
  await apiRequest(`/agent/sessions/${sessionId}`, { method: "DELETE" })
}
