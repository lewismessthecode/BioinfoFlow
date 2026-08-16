import { apiRequest, buildApiUrl } from "@/lib/api"

import type {
  AgentCommand,
  AgentPermissionMode,
  AgentSessionStatus,
  AgentWorkspaceAccess,
  JsonObject,
  SessionSnapshot,
  AgentExecutionScope,
} from "./contracts"
import { decodeAgentSnapshot } from "./protocol"

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

export type AgentArtifactResource = {
  kind: "stored_file"
  filename: string
  mime_type: string
  size_bytes: number
  sha256: string
}

export type AgentArtifact = {
  id: string
  session_id: string
  run_id: string | null
  type: string
  title: string
  summary: string | null
  payload: JsonObject | null
  resource_ref: AgentArtifactResource | null
  created_at: string
  updated_at: string
}

export type AgentArtifactContent = {
  blob: Blob
  filename: string
  mediaType: string
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
  provider?: string
  model?: string
  executionScope?: AgentExecutionScope
}) {
  const response = await apiRequest<unknown>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId ?? null,
      title: input.title,
      permission_mode: input.permissionMode,
      workspace_access: input.workspaceAccess,
      model_id: input.modelId,
      provider: input.provider,
      model: input.model,
      execution_scope: input.executionScope,
    }),
  })
  return requireAgentSnapshot(response.data)
}

export async function getAgentSnapshot(sessionId: string) {
  const response = await apiRequest<unknown>(
    `/agent/sessions/${sessionId}/snapshot`,
  )
  return requireAgentSnapshot(response.data)
}

export async function getAgentArtifact(
  artifactId: string,
  options?: { signal?: AbortSignal },
) {
  const response = await apiRequest<AgentArtifact>(
    `/agent/artifacts/${artifactId}`,
    options,
  )
  return response.data
}

export async function fetchAgentArtifactContent(
  artifactId: string,
  options?: { signal?: AbortSignal },
): Promise<AgentArtifactContent> {
  const response = await fetch(
    buildApiUrl(`/agent/artifacts/${artifactId}/download`),
    { credentials: "include", signal: options?.signal },
  )
  if (!response.ok) {
    throw new Error(response.statusText || "Artifact download failed")
  }

  const blob = await response.blob()
  return {
    blob,
    filename:
      contentDispositionFilename(response.headers.get("content-disposition")) ??
      `artifact-${artifactId}`,
    mediaType: (response.headers.get("content-type") ?? blob.type)
      .split(";", 1)[0]
      .trim()
      .toLowerCase(),
  }
}

export async function updateAgentSession(
  sessionId: string,
  updates: {
    title?: string | null
    permissionMode?: AgentPermissionMode
    workspaceAccess?: AgentWorkspaceAccess
    status?: Extract<AgentSessionStatus, "active" | "archived">
    modelId?: string
  },
) {
  const response = await apiRequest<unknown>(
    `/agent/sessions/${sessionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        title: updates.title,
        permission_mode: updates.permissionMode,
        workspace_access: updates.workspaceAccess,
        status: updates.status,
        model_id: updates.modelId,
      }),
    },
  )
  return requireAgentSnapshot(response.data)
}

export async function dispatchAgentCommand(
  sessionId: string,
  command: AgentCommand,
) {
  const response = await apiRequest<unknown>(
    `/agent/sessions/${sessionId}/commands`,
    { method: "POST", body: JSON.stringify(command) },
  )
  return requireAgentSnapshot(response.data)
}

export async function deleteAgentSession(sessionId: string) {
  await apiRequest(`/agent/sessions/${sessionId}`, { method: "DELETE" })
}

function contentDispositionFilename(value: string | null) {
  if (!value) return null
  const encoded = value.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const quoted = value.match(/filename="([^"]+)"/i)?.[1]
  const plain = value.match(/filename=([^;]+)/i)?.[1]
  const raw = encoded ?? quoted ?? plain
  if (!raw) return null

  let decoded = raw.trim().replace(/^"|"$/g, "")
  if (encoded) {
    try {
      decoded = decodeURIComponent(decoded)
    } catch {
      // Keep the server-provided name when percent-decoding fails.
    }
  }
  return decoded.split(/[\\/]/).pop() || null
}

function requireAgentSnapshot(value: unknown): SessionSnapshot {
  const decoded = decodeAgentSnapshot(value)
  if (!decoded.ok) throw new Error("Invalid Agent snapshot payload")
  return decoded.value
}
