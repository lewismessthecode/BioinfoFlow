import { apiRequest, buildApiUrl } from "@/lib/api"

import type {
  AgentCommand,
  AgentEnvironmentScope,
  AgentPermissionMode,
  AgentSessionStatus,
  AgentWorkspaceAccess,
  JsonObject,
  SessionSnapshot,
} from "./contracts"
import { requirePresentationSnapshot } from "./transport/presentation-contract"

export type AgentModelSelection =
  | { modelId: string; provider?: never; model?: never }
  | { modelId?: never; provider: string; model: string }

export type AgentSessionUpdates = {
  title?: string | null
  permissionMode?: AgentPermissionMode
  workspaceAccess?: AgentWorkspaceAccess
  model?: AgentModelSelection
  environmentScope?: AgentEnvironmentScope
  status?: Extract<AgentSessionStatus, "active" | "archived">
}

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
  environmentScope?: AgentEnvironmentScope
}) {
  const response = await apiRequest<SessionSnapshot>("/agent/sessions", {
    method: "POST",
    body: JSON.stringify({
      project_id: input.projectId ?? null,
      title: input.title,
      permission_mode: input.permissionMode,
      workspace_access: input.workspaceAccess,
      model_id: input.modelId,
      provider: input.provider,
      model: input.model,
      environment_scope: input.environmentScope,
    }),
  })
  return response.data
}

export async function getAgentSnapshot(sessionId: string) {
  const response = await apiRequest<SessionSnapshot>(
    `/agent/sessions/${sessionId}/snapshot`,
  )
  return requirePresentationSnapshot(response.data)
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
  updates: AgentSessionUpdates,
) {
  const response = await apiRequest<SessionSnapshot>(
    `/agent/sessions/${sessionId}`,
    {
      method: "PATCH",
      body: JSON.stringify({
        title: updates.title,
        permission_mode: updates.permissionMode,
        workspace_access: updates.workspaceAccess,
        model_id: updates.model?.modelId,
        provider: updates.model?.provider,
        model: updates.model?.model,
        environment_scope: updates.environmentScope,
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
