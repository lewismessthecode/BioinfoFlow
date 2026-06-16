import { apiRequest } from "@/lib/api"
import type {
  AgentActionDecision,
  AgentAnswer,
  AgentFsFile,
  AgentFsTree,
  AgentMode,
  AgentModelSelection,
  AgentPermissionMode,
  AgentRuntimeArtifact,
  AgentRuntimeSession,
  AgentRuntimeStatePayload,
  AgentRuntimeTurn,
} from "./types"

type CreateAgentRuntimeSessionInput = {
  projectId?: string | null
  title?: string
  permissionMode?: AgentPermissionMode
  mode?: AgentMode
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
      mode: input.mode,
      model_selection: input.modelSelection,
    }),
  })
  return response.data
}

export const updateAgentRuntimeSessionMode = async (
  sessionId: string,
  mode: AgentMode,
) => {
  const response = await apiRequest<AgentRuntimeSession>(
    `/agent/sessions/${sessionId}`,
    { method: "PATCH", body: JSON.stringify({ mode }) },
  )
  return response.data
}

export const updateAgentRuntimeSessionPermissionMode = async (
  sessionId: string,
  permissionMode: AgentPermissionMode,
) => {
  const response = await apiRequest<AgentRuntimeSession>(
    `/agent/sessions/${sessionId}`,
    { method: "PATCH", body: JSON.stringify({ permission_mode: permissionMode }) },
  )
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
  input: { decision: AgentActionDecision; answer?: AgentAnswer; note?: string },
) => {
  await apiRequest(`/agent/actions/${actionId}/decision`, {
    method: "POST",
    body: JSON.stringify({
      decision: input.decision,
      answer: input.answer,
      note: input.note,
    }),
  })
}

export const getAgentFsTree = async (
  path?: string | null,
  projectId?: string | null,
) => {
  const response = await apiRequest<AgentFsTree>("/agent/fs/tree", {
    params: {
      ...(path ? { path } : {}),
      ...(!path && projectId ? { project_id: projectId } : {}),
    },
  })
  return response.data
}

export const getAgentFsFile = async (path: string) => {
  const response = await apiRequest<AgentFsFile>("/agent/fs/file", {
    params: { path },
  })
  return response.data
}

export const getAgentRuntimeState = async (sessionId: string) => {
  const response = await apiRequest<AgentRuntimeStatePayload>(
    `/agent/sessions/${sessionId}/state`,
  )
  return response.data
}

export const listAgentRuntimeSessionArtifacts = async (sessionId: string) => {
  const response = await apiRequest<AgentRuntimeArtifact[]>(
    `/agent/sessions/${sessionId}/artifacts`,
  )
  return response.data
}
