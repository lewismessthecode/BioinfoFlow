import { apiRequest } from "@/lib/api"
import type {
  AgentModelSelection,
  AgentPermissionMode,
  AgentRuntimeSession,
  AgentRuntimeStatePayload,
  AgentRuntimeTurn,
} from "./types"

export type CreateAgentRuntimeSessionInput = {
  projectId?: string | null
  title?: string
  permissionMode?: AgentPermissionMode
  modelSelection?: AgentModelSelection | null
}

export const listAgentRuntimeSessions = async (projectId?: string | null) => {
  const response = await apiRequest<AgentRuntimeSession[]>("/agent/sessions", {
    params: projectId ? { project_id: projectId } : undefined,
  })
  return response.data
}

export const createAgentRuntimeSession = async (
  input: CreateAgentRuntimeSessionInput,
) => {
  const response = await apiRequest<AgentRuntimeSession>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId || null,
      title: input.title,
      permission_mode: input.permissionMode,
      automation_mode: "assisted",
      model_selection: input.modelSelection,
    }),
  })
  return response.data
}

export const createAgentRuntimeTurn = async (input: {
  sessionId: string
  inputText: string
  modelSelection?: AgentModelSelection | null
}) => {
  const response = await apiRequest<AgentRuntimeTurn>(
    `/agent/sessions/${input.sessionId}/turns`,
    {
      method: "POST",
      body: JSON.stringify({
        input_text: input.inputText,
        model_selection: input.modelSelection,
      }),
    },
  )
  return response.data
}

export const interruptAgentRuntimeTurn = async (turnId: string) => {
  const response = await apiRequest<AgentRuntimeTurn>(
    `/agent/turns/${turnId}/interrupt`,
    { method: "POST" },
  )
  return response.data
}

export const decideAgentRuntimeAction = async (
  actionId: string,
  decision: "approve" | "reject",
) => {
  await apiRequest(`/agent/actions/${actionId}/decision`, {
    method: "POST",
    body: JSON.stringify({ decision }),
  })
}

export const getAgentRuntimeState = async (sessionId: string) => {
  const response = await apiRequest<AgentRuntimeStatePayload>(
    `/agent/sessions/${sessionId}/state`,
  )
  return response.data
}
