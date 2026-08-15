import { apiRequest, buildApiUrl } from "@/lib/api"

import type {
  InputAttachmentRefPart,
  InputPart,
  InputTextPart,
} from "./contracts"

export type AgentContextSearchScope = "mixed" | "file" | "workflow" | "run"
export type AgentContextKind =
  | "attachment"
  | "file"
  | "directory"
  | "workflow"
  | "run"
export type AgentContextReferencePart = Exclude<InputPart, InputTextPart>

export type AgentContextSearchItem = {
  id: string
  kind: Exclude<AgentContextKind, "attachment">
  label: string
  detail: string | null
  input_part: AgentContextReferencePart
}

export type AgentContextSearchResult = {
  results: AgentContextSearchItem[]
  counts: Record<string, number>
  next_cursor: string | null
}

export type AgentContextInput = {
  id: string
  kind: AgentContextKind
  label: string
  detail?: string | null
  input_part: AgentContextReferencePart
}

export type AgentAttachmentUploadKind = "file" | "folder" | "image"
export type AgentAttachmentUploadSource = "upload" | "clipboard"

type AgentAttachmentUploadRecord = {
  id: string
}

export async function searchAgentContext(input: {
  query: string
  scope?: AgentContextSearchScope
  projectId?: string | null
  sessionId?: string | null
  cursor?: string | null
  signal?: AbortSignal
}) {
  const params: Record<string, string> = { q: input.query }
  if (input.scope) params.scope = input.scope
  if (input.projectId) params.project_id = input.projectId
  if (input.sessionId) params.session_id = input.sessionId
  if (input.cursor) params.cursor = input.cursor

  const response = await apiRequest<AgentContextSearchResult>(
    "/agent/context/search",
    { params, signal: input.signal },
  )
  return response.data
}

export async function uploadAgentAttachments(input: {
  sessionId: string
  kind: AgentAttachmentUploadKind
  files: File[]
  relativePaths?: string[]
  source?: AgentAttachmentUploadSource
}): Promise<InputAttachmentRefPart[]> {
  const body = new FormData()
  body.append("kind", input.kind)
  body.append("source", input.source ?? "upload")
  for (const file of input.files) body.append("files", file)
  for (const path of input.relativePaths ?? []) {
    body.append("relative_paths", path)
  }

  const response = await apiRequest<AgentAttachmentUploadRecord[]>(
    `/agent/sessions/${input.sessionId}/attachments`,
    { method: "POST", body },
  )
  return response.data.map((attachment) => ({
    type: "attachment_ref",
    attachment_id: attachment.id,
  }))
}

export async function deleteAgentAttachment(attachmentId: string) {
  await apiRequest(`/agent/attachments/${attachmentId}`, { method: "DELETE" })
}

export function agentAttachmentPreviewUrl(attachmentId: string) {
  return buildApiUrl(`/agent/attachments/${attachmentId}/preview`)
}
