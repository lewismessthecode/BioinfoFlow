import { ApiError, apiRequest, buildApiUrl } from "@/lib/api"
import type { ProjectWorkflowGroup, Workflow } from "@/lib/types"
import { buildHubWorkflowGroups } from "@/lib/workflow-groups"
import {
  agentExecutionScopeForRequest,
  agentExecutionTargetForRequest,
} from "./execution-target"
import type {
  AgentActionDecision,
  AgentAnswer,
  AgentExecutionScope,
  AgentExecutionTarget,
  AgentFsFile,
  AgentFsTree,
  AgentMode,
  AgentModelSelection,
  AgentPermissionMode,
  AgentPendingStrategy,
  AgentRuntimeArtifact,
  AgentRuntimeAttachment,
  AgentRuntimeContextSearchResponse,
  AgentRuntimeContextSearchScope,
  AgentRuntimeInputPart,
  AgentRuntimeSession,
  AgentRuntimeSteerOutcome,
  AgentRuntimeSteerResult,
  AgentRuntimeSkill,
  AgentRuntimeStatePayload,
  AgentRuntimeTurn,
  AgentRuntimeWorkflowMention,
} from "./types"

export const uploadAgentRuntimeAttachment = async (input: {
  sessionId: string
  kind: "file" | "folder" | "image"
  files: File[]
  relativePaths?: string[]
  source?: "upload" | "clipboard"
}) => {
  const body = new FormData()
  body.append("kind", input.kind)
  body.append("source", input.source ?? "upload")
  input.files.forEach((file) => body.append("files", file))
  input.relativePaths?.forEach((path) => body.append("relative_paths", path))
  const response = await apiRequest<AgentRuntimeAttachment[]>(
    `/agent/sessions/${input.sessionId}/attachments`,
    { method: "POST", body },
  )
  return response.data
}

export const deleteAgentRuntimeAttachment = async (attachmentId: string) => {
  await apiRequest(`/agent/attachments/${attachmentId}`, { method: "DELETE" })
}

export const agentRuntimeAttachmentPreviewUrl = (attachmentId: string) =>
  buildApiUrl(`/agent/attachments/${attachmentId}/preview`)

export const searchAgentRuntimeContext = async (input: {
  query: string
  scope?: AgentRuntimeContextSearchScope
  projectId?: string | null
  sessionId?: string | null
  cursor?: string | null
  signal?: AbortSignal
}) => {
  const params: Record<string, string> = { q: input.query }
  if (input.scope) params.scope = input.scope
  if (input.projectId) params.project_id = input.projectId
  if (input.sessionId) params.session_id = input.sessionId
  if (input.cursor) params.cursor = input.cursor
  const response = await apiRequest<AgentRuntimeContextSearchResponse>(
    "/agent/context/search",
    { params, signal: input.signal },
  )
  return response.data
}

type CreateAgentRuntimeSessionInput = {
  projectId?: string | null
  title?: string
  permissionMode?: AgentPermissionMode
  mode?: AgentMode
  modelSelection?: AgentModelSelection | null
  executionTarget?: AgentExecutionTarget | null
  executionScope?: AgentExecutionScope | null
  metadata?: Record<string, unknown> | null
}

export const listAgentRuntimeSessions = async (
  projectId?: string | null,
  options?: { includeChildren?: boolean; parentSessionId?: string },
) => {
  const params: Record<string, string | boolean> = {}
  if (projectId) params.project_id = projectId
  if (options?.parentSessionId) params.parent_session_id = options.parentSessionId
  if (options?.includeChildren) params.include_children = true
  const response = await apiRequest<AgentRuntimeSession[]>("/agent/sessions", {
    params: Object.keys(params).length ? params : undefined,
  })
  return response.data
}

export const listAgentRuntimeSkills = async () => {
  const response = await apiRequest<{ skills: AgentRuntimeSkill[] }>("/agent/skills")
  return response.data.skills
}

export const listAgentRuntimeWorkflowMentions = async (
  projectId?: string | null,
) => {
  if (projectId) {
    const response = await apiRequest<ProjectWorkflowGroup[]>(
      `/projects/${projectId}/workflows`,
    )
    return workflowMentionsFromProjectGroups(response.data, projectId)
  }

  const response = await apiRequest<Workflow[]>("/workflows", {
    params: { limit: 200 },
  })
  return workflowMentionsFromHubGroups(buildHubWorkflowGroups(response.data))
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
      execution_target: agentExecutionTargetForRequest(input.executionTarget),
      execution_scope: agentExecutionScopeForRequest(input.executionScope),
      metadata: input.metadata,
    }),
  })
  return response.data
}

function workflowMentionsFromProjectGroups(
  groups: ProjectWorkflowGroup[],
  projectId: string,
): AgentRuntimeWorkflowMention[] {
  return groups.flatMap((group) => {
    const pinnedId = group.pinned_workflow.id
    return group.versions.map((workflow) =>
      workflowMentionFromWorkflow(workflow, {
        scope: "project",
        projectId,
        pinned: workflow.id === pinnedId,
      }),
    )
  })
}

function workflowMentionsFromHubGroups(
  groups: ReturnType<typeof buildHubWorkflowGroups>,
): AgentRuntimeWorkflowMention[] {
  return groups.flatMap((group) => {
    const latestId = group.latest_workflow.id
    return group.versions.map((workflow) =>
      workflowMentionFromWorkflow(workflow, {
        scope: "global",
        projectId: null,
        pinned: workflow.id === latestId,
      }),
    )
  })
}

function workflowMentionFromWorkflow(
  workflow: Workflow,
  {
    scope,
    projectId,
    pinned,
  }: {
    scope: AgentRuntimeWorkflowMention["scope"]
    projectId: string | null
    pinned: boolean
  },
): AgentRuntimeWorkflowMention {
  return {
    id: workflow.id,
    name: workflow.name,
    version: workflow.version,
    engine: workflow.engine,
    source: workflow.source,
    description: workflow.description ?? null,
    scope,
    projectId,
    pinned,
  }
}

export const getAgentRuntimeSession = async (sessionId: string) => {
  const response = await apiRequest<AgentRuntimeSession>(
    `/agent/sessions/${sessionId}`,
  )
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
  pendingStrategy?: AgentPendingStrategy,
) => {
  const response = await apiRequest<AgentRuntimeSession>(
    `/agent/sessions/${sessionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        permission_mode: permissionMode,
        ...(pendingStrategy ? { pending_strategy: pendingStrategy } : {}),
      }),
    },
  )
  return response.data
}

export const updateAgentRuntimeSessionMetadata = async (
  sessionId: string,
  metadata: Record<string, unknown> | null,
  executionTarget?: AgentExecutionTarget | null,
  executionScope?: AgentExecutionScope | null,
) => {
  const requestExecutionTarget =
    executionTarget === null
      ? null
      : agentExecutionTargetForRequest(executionTarget)
  const response = await apiRequest<AgentRuntimeSession>(
    `/agent/sessions/${sessionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        metadata,
        ...(executionTarget !== undefined
          ? { execution_target: requestExecutionTarget }
          : {}),
        ...(executionScope !== undefined
          ? { execution_scope: agentExecutionScopeForRequest(executionScope) }
          : {}),
      }),
    },
  )
  return response.data
}

export const createAgentRuntimeTurn = async (input: {
  sessionId: string
  inputText: string
  inputParts?: AgentRuntimeInputPart[] | null
  activeSkillNames?: string[] | null
  modelSelection?: AgentModelSelection | null
  executionTarget?: AgentExecutionTarget | null
  executionScope?: AgentExecutionScope | null
  metadata?: Record<string, unknown> | null
}) => {
  const response = await apiRequest<AgentRuntimeTurn>(
    `/agent/sessions/${input.sessionId}/turns`,
    {
      method: "POST",
      body: JSON.stringify({
        input_text: input.inputText,
        input_parts: agentRuntimeInputPartsForRequest(input.inputParts),
        ...(input.activeSkillNames?.length
          ? { active_skill_names: input.activeSkillNames }
          : {}),
        model_selection: input.modelSelection,
        execution_target: agentExecutionTargetForRequest(input.executionTarget),
        execution_scope: agentExecutionScopeForRequest(input.executionScope),
        metadata: input.metadata,
      }),
    },
  )
  return response.data
}

function agentRuntimeInputPartsForRequest(
  inputParts?: AgentRuntimeInputPart[] | null,
): AgentRuntimeInputPart[] | null | undefined {
  if (!inputParts) return inputParts
  return inputParts.map((part) => {
    const discriminator = "type" in part ? part.type : "kind" in part ? part.kind : null
    if (discriminator === "text") return part
    if (discriminator === "workflow_ref" && "kind" in part) {
      const requestPart: AgentRuntimeInputPart = { kind: "workflow_ref" }
      if (Object.hasOwn(part, "workflow_id")) {
        requestPart.workflow_id = part.workflow_id ?? null
      }
      if (Object.hasOwn(part, "project_id")) {
        requestPart.project_id = part.project_id ?? null
      }
      if (Object.hasOwn(part, "scope")) {
        requestPart.scope = part.scope
      }
      return requestPart
    }
    if (!("type" in part)) return part
    const requestPart = { type: part.type } as Record<string, unknown>
    const requestKeys: Record<string, string[]> = {
      file_ref: ["attachment_id", "project_id", "path", "label", "include_content"],
      directory_ref: ["attachment_id", "project_id", "path", "label"],
      image_ref: ["attachment_id", "detail"],
      run_ref: ["run_id"],
      workflow_ref: ["workflow_id", "project_id", "scope"],
    }
    for (const key of requestKeys[part.type] ?? []) {
      if (Object.hasOwn(part, key)) requestPart[key] = (part as unknown as Record<string, unknown>)[key]
    }
    return requestPart as AgentRuntimeInputPart
  })
}

export const interruptAgentRuntimeTurn = async (turnId: string) => {
  const response = await apiRequest<AgentRuntimeTurn>(
    `/agent/turns/${turnId}/interrupt`,
    { method: "POST" },
  )
  return response.data
}

export const steerAgentRuntimeTurn = async (
  turnId: string,
  input: {
    inputText: string
    inputParts?: AgentRuntimeInputPart[] | null
    activeSkillNames?: string[] | null
    metadata?: Record<string, unknown> | null
  },
): Promise<AgentRuntimeSteerOutcome> => {
  try {
    const response = await apiRequest<AgentRuntimeSteerResult>(
      `/agent/turns/${turnId}/steer`,
      {
        method: "POST",
        body: JSON.stringify({
          input_text: input.inputText,
          input_parts: agentRuntimeInputPartsForRequest(input.inputParts),
          ...(input.activeSkillNames?.length
            ? { active_skill_names: input.activeSkillNames }
            : {}),
          metadata: input.metadata,
        }),
      },
    )
    return { kind: "accepted", result: response.data }
  } catch (error) {
    if (error instanceof ApiError && error.status === 409) {
      return { kind: "sealed" }
    }
    throw error
  }
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

export const buildAgentFsDownloadUrl = (
  path: string,
  options?: { inline?: boolean },
) => buildApiUrl("/agent/fs/download", {
  path,
  inline: options?.inline ? "true" : undefined,
})

export const getAgentRuntimeState = async (
  sessionId: string,
  options?: { eventLimit?: number; eventView?: "full" | "transcript" },
) => {
  const params = {
    ...(options?.eventLimit ? { event_limit: options.eventLimit } : {}),
    ...(options?.eventView ? { event_view: options.eventView } : {}),
  }
  const response = await apiRequest<AgentRuntimeStatePayload>(
    `/agent/sessions/${sessionId}/state`,
    {
      params: Object.keys(params).length ? params : undefined,
    },
  )
  return response.data
}

export const listAgentRuntimeSessionArtifacts = async (sessionId: string) => {
  const response = await apiRequest<AgentRuntimeArtifact[]>(
    `/agent/sessions/${sessionId}/artifacts`,
  )
  return response.data
}
