import type { AgentRuntimeArtifact } from "./types"

const NON_REVIEW_ARTIFACT_TYPES = new Set([
  "command",
  "log_summary",
  "todo_list",
])

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

export function isDeliverableArtifact(artifact: AgentRuntimeArtifact) {
  if (NON_REVIEW_ARTIFACT_TYPES.has(artifact.type)) return false
  if (artifact.file_path) return true
  return DELIVERABLE_ARTIFACT_TYPES.has(artifact.type)
}

export function deliverableArtifacts(artifacts: AgentRuntimeArtifact[]) {
  return artifacts.filter(isDeliverableArtifact)
}

export function countDeliverableArtifacts(artifacts: AgentRuntimeArtifact[]) {
  return deliverableArtifacts(artifacts).length
}
