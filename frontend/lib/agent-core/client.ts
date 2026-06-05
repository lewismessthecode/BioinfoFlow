import { apiRequest } from "@/lib/api"
import type {
  AgentActionDecision,
  AgentCoreAction,
  AgentCoreArtifact,
  AgentCoreEvent,
  AgentCoreMemory,
  AgentCoreSession,
  AgentCoreTurn,
  AgentPermissionMode,
  AgentAutomationMode,
} from "@/lib/agent-core/types"

export type CreateAgentSessionInput = {
  projectId: string
  title?: string
  roleProfile?: string
  permissionMode?: AgentPermissionMode
  automationMode?: AgentAutomationMode
  defaultModelProfileId?: string
  metadata?: Record<string, unknown>
}

export type CreateAgentTurnInput = {
  sessionId: string
  inputText: string
  inputParts?: Array<Record<string, unknown>>
  modelProfileId?: string
  metadata?: Record<string, unknown>
}

export type UpdateAgentSessionInput = {
  title?: string
  roleProfile?: string
  permissionMode?: AgentPermissionMode
  automationMode?: AgentAutomationMode
  defaultModelProfileId?: string | null
  status?: AgentCoreSession["status"]
  metadata?: Record<string, unknown> | null
}

export const listAgentSessions = async (projectId?: string) => {
  const response = await apiRequest<AgentCoreSession[]>("/agent/sessions", {
    params: projectId ? { project_id: projectId } : undefined,
  })
  return response.data
}

export const createAgentSession = async (input: CreateAgentSessionInput) => {
  const response = await apiRequest<AgentCoreSession>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId,
      title: input.title,
      role_profile: input.roleProfile,
      permission_mode: input.permissionMode,
      automation_mode: input.automationMode,
      default_model_profile_id: input.defaultModelProfileId,
      metadata: input.metadata,
    }),
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
      status: updates.status,
      metadata: updates.metadata,
    }),
  })
  return response.data
}

export const deleteAgentSession = async (sessionId: string) => {
  await apiRequest(`/agent/sessions/${sessionId}`, { method: "DELETE" })
}

export const createAgentTurn = async (input: CreateAgentTurnInput) => {
  const response = await apiRequest<AgentCoreTurn>(
    `/agent/sessions/${input.sessionId}/turns`,
    {
      method: "POST",
      body: JSON.stringify({
        input_text: input.inputText,
        input_parts: input.inputParts,
        model_profile_id: input.modelProfileId,
        metadata: input.metadata,
      }),
    },
  )
  return response.data
}

export const listAgentTurns = async (sessionId: string) => {
  const response = await apiRequest<AgentCoreTurn[]>(
    `/agent/sessions/${sessionId}/turns`,
  )
  return response.data
}

export const listAgentTurnEvents = async (turnId: string, afterSeq = 0) => {
  const response = await apiRequest<AgentCoreEvent[]>(`/agent/turns/${turnId}/events`, {
    params: afterSeq > 0 ? { after_seq: afterSeq } : undefined,
  })
  return response.data
}

export const decideAgentAction = async (
  actionId: string,
  decision: AgentActionDecision,
  options?: { note?: string; modifiedInput?: Record<string, unknown> },
) => {
  const response = await apiRequest<AgentCoreAction>(
    `/agent/actions/${actionId}/decision`,
    {
      method: "POST",
      body: JSON.stringify({
        decision,
        note: options?.note,
        modified_input: options?.modifiedInput,
      }),
    },
  )
  return response.data
}

export const listAgentTurnArtifacts = async (turnId: string) => {
  const response = await apiRequest<AgentCoreArtifact[]>(
    `/agent/turns/${turnId}/artifacts`,
  )
  return response.data
}

export const listAgentMemories = async (filters: {
  projectId?: string
  status?: AgentCoreMemory["status"]
  scope?: string
  type?: string
}) => {
  const response = await apiRequest<AgentCoreMemory[]>("/agent/memories", {
    params: {
      project_id: filters.projectId,
      status: filters.status,
      scope: filters.scope,
      type: filters.type,
    },
  })
  return response.data
}

export const acceptAgentMemory = async (
  memoryId: string,
  options?: { note?: string },
) => {
  const response = await apiRequest<AgentCoreMemory>(
    `/agent/memories/${memoryId}/accept`,
    {
      method: "POST",
      body: JSON.stringify({ note: options?.note }),
    },
  )
  return response.data
}

export const rejectAgentMemory = async (
  memoryId: string,
  options?: { note?: string },
) => {
  const response = await apiRequest<AgentCoreMemory>(
    `/agent/memories/${memoryId}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ note: options?.note }),
    },
  )
  return response.data
}

export const disableAgentMemory = async (
  memoryId: string,
  options?: { note?: string },
) => {
  const response = await apiRequest<AgentCoreMemory>(
    `/agent/memories/${memoryId}/disable`,
    {
      method: "POST",
      body: JSON.stringify({ note: options?.note }),
    },
  )
  return response.data
}
