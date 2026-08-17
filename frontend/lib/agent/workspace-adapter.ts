import { apiRequest, buildApiUrl } from "@/lib/api"

import {
  fetchAgentArtifactContent,
  listAgentArtifacts,
  type AgentArtifact,
} from "./client"

export type WorkspaceFileNode = {
  name: string
  path: string
  type: "file" | "directory"
  sizeBytes: number | null
  modifiedAt: string | null
  children?: WorkspaceFileNode[]
}

export type WorkspaceFilePreview = {
  path: string
  content: string
  totalLines: number
  truncated: boolean
}

export type WorkspaceArtifact = {
  id: string
  source: "session" | "workspace"
  runId: string | null
  title: string
  summary: string | null
  kind: string
  mediaType: string | null
  sizeBytes: number | null
  createdAt: string
  updatedAt: string
  payload: Record<string, unknown> | null
  resource:
    | { kind: "session"; artifactId: string }
    | { kind: "workspace"; projectId: string; path: string }
    | null
}

export type WorkspaceArtifactContent = {
  blob: Blob
  filename: string
  mediaType: string
}

export type AgentWorkspaceAdapter = {
  listFiles: (input: {
    projectId: string
    path: string
    signal?: AbortSignal
  }) => Promise<WorkspaceFileNode[]>
  readFile: (input: {
    projectId: string
    path: string
    lines?: number
    signal?: AbortSignal
  }) => Promise<WorkspaceFilePreview>
  fileDownloadUrl: (input: { projectId: string; path: string }) => string
  listArtifacts: (input: {
    sessionId?: string | null
    projectId?: string | null
    signal?: AbortSignal
  }) => Promise<WorkspaceArtifact[]>
  fetchArtifactContent: (input: {
    artifact: WorkspaceArtifact
    signal?: AbortSignal
  }) => Promise<WorkspaceArtifactContent>
}

function contentWithMediaType(
  content: WorkspaceArtifactContent,
  fallbackMediaType: string | null,
): WorkspaceArtifactContent {
  const mediaType =
    content.mediaType && content.mediaType !== "application/octet-stream"
      ? content.mediaType
      : fallbackMediaType || "application/octet-stream"
  return {
    ...content,
    mediaType,
    blob:
      content.blob.type === mediaType
        ? content.blob
        : content.blob.slice(0, content.blob.size, mediaType),
  }
}

type FileApiNode = {
  name: string
  path: string
  type: "file" | "directory"
  size_bytes?: number | null
  modified_at?: string | null
  children?: FileApiNode[] | null
}

type FileListResponse = {
  path: string
  files: FileApiNode[]
}

type FileReadResponse = {
  path: string
  content: string
  total_lines: number
  truncated: boolean
}

const DELIVERABLE_EXTENSIONS = new Set([
  "csv",
  "gif",
  "htm",
  "html",
  "jpeg",
  "jpg",
  "json",
  "md",
  "markdown",
  "pdf",
  "png",
  "svg",
  "tsv",
  "txt",
  "webp",
  "xml",
  "xls",
  "xlsx",
  "yaml",
  "yml",
])

const MEDIA_TYPES: Record<string, string> = {
  csv: "text/csv",
  gif: "image/gif",
  htm: "text/html",
  html: "text/html",
  jpeg: "image/jpeg",
  jpg: "image/jpeg",
  json: "application/json",
  md: "text/markdown",
  markdown: "text/markdown",
  pdf: "application/pdf",
  png: "image/png",
  svg: "image/svg+xml",
  tsv: "text/tab-separated-values",
  txt: "text/plain",
  webp: "image/webp",
  xml: "application/xml",
  xls: "application/vnd.ms-excel",
  xlsx: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  yaml: "application/yaml",
  yml: "application/yaml",
}

const ARTIFACT_SCAN_BATCH_SIZE = 6
const ARTIFACT_SCAN_MAX_DEPTH = 6
const ARTIFACT_SCAN_MAX_NODES = 800
const SKIPPED_ARTIFACT_DIRECTORIES = new Set([
  ".git",
  ".next",
  ".turbo",
  ".venv",
  "__pycache__",
  "node_modules",
  "venv",
])

function mapFileNode(node: FileApiNode): WorkspaceFileNode {
  return {
    name: node.name,
    path: node.path,
    type: node.type,
    sizeBytes: node.size_bytes ?? null,
    modifiedAt: node.modified_at ?? null,
    children: node.children?.map(mapFileNode),
  }
}

function mapSessionArtifact(artifact: AgentArtifact): WorkspaceArtifact {
  return {
    id: `session:${artifact.id}`,
    source: "session",
    runId: artifact.run_id,
    title: artifact.title,
    summary: artifact.summary,
    kind: artifact.type,
    mediaType: artifact.resource_ref?.mime_type ?? null,
    sizeBytes: artifact.resource_ref?.size_bytes ?? null,
    createdAt: artifact.created_at,
    updatedAt: artifact.updated_at,
    payload: artifact.payload,
    resource: artifact.resource_ref
      ? { kind: "session", artifactId: artifact.id }
      : null,
  }
}

function workspaceDeliverable(
  node: FileApiNode,
  projectId: string,
): WorkspaceArtifact | null {
  if (node.type !== "file") return null
  const extension = node.name.split(".").pop()?.toLowerCase() ?? ""
  if (!DELIVERABLE_EXTENSIONS.has(extension)) return null
  const timestamp = node.modified_at ?? new Date(0).toISOString()
  return {
    id: `workspace:${projectId}:${node.path}`,
    source: "workspace",
    runId: null,
    title: node.name,
    summary: node.path === node.name ? null : node.path,
    kind: extension || "file",
    mediaType: MEDIA_TYPES[extension] ?? null,
    sizeBytes: node.size_bytes ?? null,
    createdAt: timestamp,
    updatedAt: timestamp,
    payload: null,
    resource: { kind: "workspace", projectId, path: node.path },
  }
}

export function workspaceArtifactSelectionId(artifact: WorkspaceArtifact) {
  return artifact.resource?.kind === "session"
    ? artifact.resource.artifactId
    : artifact.id
}

async function discoverWorkspaceDeliverables(input: {
  projectId: string
  signal?: AbortSignal
}) {
  const queue: Array<{ path: string; depth: number }> = [{ path: ".", depth: 0 }]
  const deliverables: WorkspaceArtifact[] = []
  let visitedNodes = 0

  while (queue.length > 0 && visitedNodes < ARTIFACT_SCAN_MAX_NODES) {
    const batch = queue.splice(0, ARTIFACT_SCAN_BATCH_SIZE)
    const responses = await Promise.allSettled(
      batch.map(({ path }) =>
        apiRequest<FileListResponse>("/files", {
          params: { project_id: input.projectId, path, recursive: false },
          signal: input.signal,
        }),
      ),
    )
    for (let index = 0; index < responses.length; index += 1) {
      const response = responses[index]
      if (response.status !== "fulfilled") continue
      const depth = batch[index].depth
      for (const node of response.value.data.files) {
        visitedNodes += 1
        if (visitedNodes > ARTIFACT_SCAN_MAX_NODES) break
        if (node.type === "directory") {
          if (
            depth < ARTIFACT_SCAN_MAX_DEPTH &&
            !node.name.startsWith(".") &&
            !SKIPPED_ARTIFACT_DIRECTORIES.has(node.name)
          ) {
            queue.push({ path: node.path, depth: depth + 1 })
          }
          continue
        }
        const artifact = workspaceDeliverable(node, input.projectId)
        if (artifact) deliverables.push(artifact)
      }
    }
  }

  return deliverables
}

export const bioinfoFlowAgentWorkspaceAdapter: AgentWorkspaceAdapter = {
  async listFiles({ projectId, path, signal }) {
    const response = await apiRequest<FileListResponse>("/files", {
      params: { project_id: projectId, path, recursive: false },
      signal,
    })
    return response.data.files.map(mapFileNode)
  },

  async readFile({ projectId, path, lines = 1200, signal }) {
    const response = await apiRequest<FileReadResponse>("/files/read", {
      params: { project_id: projectId, path, lines },
      signal,
    })
    return {
      path: response.data.path,
      content: response.data.content,
      totalLines: response.data.total_lines,
      truncated: response.data.truncated,
    }
  },

  fileDownloadUrl({ projectId, path }) {
    return buildApiUrl("/files/download", {
      project_id: projectId,
      path,
    })
  },

  async listArtifacts({ sessionId, projectId, signal }) {
    const [sessionArtifacts, projectFiles] = await Promise.all([
      sessionId
        ? listAgentArtifacts(sessionId, { signal }).then((items) =>
            items.map(mapSessionArtifact),
          )
        : Promise.resolve([]),
      projectId
        ? discoverWorkspaceDeliverables({ projectId, signal })
        : Promise.resolve([]),
    ])
    const sessionPaths = new Set(
      sessionArtifacts
        .map((artifact) => artifact.summary)
        .filter((value): value is string => Boolean(value)),
    )
    return [
      ...sessionArtifacts,
      ...projectFiles.filter((artifact) => !artifact.summary || !sessionPaths.has(artifact.summary)),
    ]
  },

  async fetchArtifactContent({ artifact, signal }) {
    if (artifact.resource?.kind === "session") {
      const content = await fetchAgentArtifactContent(
        artifact.resource.artifactId,
        { signal },
      )
      return contentWithMediaType(content, artifact.mediaType)
    }
    if (artifact.resource?.kind === "workspace") {
      const response = await fetch(
        buildApiUrl("/files/download", {
          project_id: artifact.resource.projectId,
          path: artifact.resource.path,
        }),
        { credentials: "include", signal },
      )
      if (!response.ok) throw new Error(response.statusText || "Artifact download failed")
      const blob = await response.blob()
      const responseMediaType = (response.headers.get("content-type") ?? blob.type)
        .split(";", 1)[0]
        .trim()
        .toLowerCase()
      return contentWithMediaType({
        blob,
        filename: artifact.title,
        mediaType:
          responseMediaType && responseMediaType !== "application/octet-stream"
            ? responseMediaType
            : artifact.mediaType || "application/octet-stream",
      }, artifact.mediaType)
    }
    throw new Error("Artifact has no previewable resource")
  },
}
