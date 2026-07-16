import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"

const WRITE_BYTES_SUMMARY_PATTERN = /^\s*wrote\s+[\d,.]+\s+(?:bytes?|[kmgt]?b)\s*$/i

export function artifactFilePath(artifact: AgentRuntimeArtifact) {
  const payload = artifact.payload ?? {}
  if (typeof payload.path === "string" && payload.path.trim()) return payload.path
  return artifact.file_path || null
}

export function artifactDisplayTitle(artifact: AgentRuntimeArtifact) {
  const path = artifactFilePath(artifact)
  const title = artifact.title?.trim()
  const candidate = title || path || artifact.type
  return basename(candidate) || candidate
}

export function artifactDisplaySubtitle(
  artifact: AgentRuntimeArtifact,
  typeLabel: string,
) {
  const summary = displayableArtifactSummary(artifact.summary)
  if (summary) return summary

  const parts = [typeLabel]
  const size = artifactDisplaySize(artifact)
  const path = artifactFilePath(artifact)
  const title = artifactDisplayTitle(artifact)
  const friendlyPath = path ? friendlyArtifactPath(path) : null

  if (size) parts.push(size)
  if (friendlyPath && friendlyPath !== title) parts.push(friendlyPath)

  return parts.join(" · ")
}

function displayableArtifactSummary(summary: string | null | undefined) {
  const trimmed = summary?.trim()
  if (!trimmed) return null
  if (WRITE_BYTES_SUMMARY_PATTERN.test(trimmed)) return null
  return trimmed
}

function artifactDisplaySize(artifact: AgentRuntimeArtifact) {
  const payload = artifact.payload ?? {}
  const size = typeof payload.size === "number" ? payload.size : null
  if (size === null || !Number.isFinite(size) || size < 0) return null
  if (size < 1024) return `${size} B`
  if (size < 1024 * 1024) return `${formatNumber(size / 1024)} KB`
  if (size < 1024 * 1024 * 1024) return `${formatNumber(size / 1024 / 1024)} MB`
  return `${formatNumber(size / 1024 / 1024 / 1024)} GB`
}

function formatNumber(value: number) {
  return value >= 10 ? value.toFixed(0) : value.toFixed(1)
}

function friendlyArtifactPath(path: string) {
  const normalized = path.trim().replace(/^\/+/, "")
  if (!normalized) return null
  return normalized.replace(/^workspace\//, "")
}

function basename(value: string) {
  const trimmed = value.trim().replace(/\/+$/, "")
  return trimmed.split("/").filter(Boolean).pop() ?? ""
}
