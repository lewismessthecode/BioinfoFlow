import type { AgentRuntimeArtifact } from "./types"

const DELIVERABLE_ARTIFACT_TYPES = new Set([
  "file",
  "html",
  "image",
  "pdf",
  "report",
  "markdown",
  "sheet",
  "spreadsheet",
])

function isDeliverableArtifact(artifact: AgentRuntimeArtifact) {
  if (!DELIVERABLE_ARTIFACT_TYPES.has(artifact.type)) return false
  return hasRenderableFileSource(artifact)
}

export function deliverableArtifacts(artifacts: AgentRuntimeArtifact[]) {
  return artifacts.filter(isDeliverableArtifact)
}

function hasRenderableFileSource(artifact: AgentRuntimeArtifact) {
  if (isNonEmptyString(artifact.file_path)) return true

  const payload = artifact.payload ?? {}
  if (isNonEmptyString(payload.path)) return true
  if (isNonEmptyString(payload.url) || isNonEmptyString(payload.href)) return true
  if (typeof payload.content === "string") return true
  if (Array.isArray(payload.rows)) return true

  const resource = artifact.resource_ref ?? {}
  return isNonEmptyString(resource.url) || isNonEmptyString(resource.href)
}

function isNonEmptyString(value: unknown) {
  return typeof value === "string" && value.trim().length > 0
}
