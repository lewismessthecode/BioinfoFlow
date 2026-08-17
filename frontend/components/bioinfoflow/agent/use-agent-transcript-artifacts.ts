"use client"

import { useEffect, useMemo, useState } from "react"

import type {
  ArtifactTranscriptBlock,
  ConversationRunAudit,
  ConversationViewModel,
  TranscriptBlock,
} from "@/lib/agent/conversation-model/types"
import {
  type AgentWorkspaceAdapter,
  type WorkspaceArtifact,
  workspaceArtifactSelectionId,
} from "@/lib/agent/workspace-adapter"

type SupplementalArtifactInput = {
  artifacts: readonly WorkspaceArtifact[]
  runs: readonly ConversationRunAudit[]
  transcript: readonly TranscriptBlock[]
  transcriptArtifactIds: ReadonlySet<string>
}

const MUTATING_TOOL_NAMES = new Set(["bash", "edit", "write"])
const PATH_MUTATING_TOOL_NAMES = new Set(["edit", "write"])

export function buildSupplementalArtifactBlocks({
  artifacts,
  runs,
  transcript,
  transcriptArtifactIds,
}: SupplementalArtifactInput): ArtifactTranscriptBlock[] {
  const runsById = new Map(runs.map((run) => [run.id, run]))

  return artifacts
    .flatMap((artifact) => {
      const selectionId = workspaceArtifactSelectionId(artifact)
      if (transcriptArtifactIds.has(selectionId)) return []
      const runId = artifact.runId && runsById.has(artifact.runId)
        ? artifact.runId
        : workspaceArtifactRunId(artifact, runs, transcript)
      if (!runId) return []
      return [{ artifact, runId, selectionId }]
    })
    .sort((left, right) =>
      left.artifact.createdAt.localeCompare(right.artifact.createdAt),
    )
    .map(({ artifact, runId, selectionId }) => ({
      type: "artifact",
      id: `workspace-artifact:${artifact.id}`,
      runId,
      createdAt: artifact.createdAt,
      artifactId: selectionId,
      title: artifact.title,
      mediaType: artifact.mediaType,
    }))
}

export function useAgentTranscriptArtifacts({
  adapter,
  sessionId,
  projectId,
  view,
}: {
  adapter: AgentWorkspaceAdapter
  sessionId: string
  projectId: string | null
  view: ConversationViewModel | null
}) {
  const requestKey = useMemo(() => {
    if (!view) return "unavailable"
    const runs = view.runs
      .map((run) => `${run.id}:${run.startedAt ?? ""}:${run.completedAt ?? ""}:${run.status}`)
      .join("|")
    const artifactIds = view.transcript
      .flatMap((block) => (block.type === "artifact" ? [block.artifactId] : []))
      .join("|")
    return [
      sessionId,
      projectId ?? "",
      view.activeWork ? `${view.activeWork.runId}:${view.activeWork.status}` : "idle",
      runs,
      artifactIds,
    ].join("::")
  }, [projectId, sessionId, view])
  const [state, setState] = useState<{
    key: string
    artifacts: ArtifactTranscriptBlock[]
  }>({ key: "", artifacts: [] })

  useEffect(() => {
    if (!view || view.activeWork || view.runs.length === 0) return
    const controller = new AbortController()
    const transcriptArtifactIds = new Set(
      view.transcript.flatMap((block) =>
        block.type === "artifact" ? [block.artifactId] : [],
      ),
    )
    void adapter
      .listArtifacts({ sessionId, projectId, signal: controller.signal })
      .then((artifacts) => {
        if (controller.signal.aborted) return
        setState({
          key: requestKey,
          artifacts: buildSupplementalArtifactBlocks({
            artifacts,
            runs: view.runs,
            transcript: view.transcript,
            transcriptArtifactIds,
          }),
        })
      })
      .catch(() => {
        if (!controller.signal.aborted) {
          setState({ key: requestKey, artifacts: [] })
        }
      })
    return () => controller.abort()
  }, [adapter, projectId, requestKey, sessionId, view])

  return state.key === requestKey ? state.artifacts : []
}

function timestamp(value: string | null) {
  if (!value) return null
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value)
    ? value
    : `${value}Z`
  const parsed = Date.parse(normalized)
  return Number.isFinite(parsed) ? parsed : null
}

function workspaceArtifactRunId(
  artifact: WorkspaceArtifact,
  runs: readonly ConversationRunAudit[],
  transcript: readonly TranscriptBlock[],
) {
  if (artifact.resource?.kind !== "workspace") return null
  const pathMatches = transcript.flatMap((block) => {
    if (block.type !== "activity_group" || !block.runId) return []
    const matched = block.activities.some(
      (activity) =>
        activity.status === "completed" &&
        PATH_MUTATING_TOOL_NAMES.has(activity.name) &&
        activity.details?.some(
          (detail) =>
            detail.kind === "path" &&
            !detail.truncated &&
            pathMatchesArtifact(detail.value, artifact),
        ),
    )
    return matched ? [block.runId] : []
  })
  if (pathMatches.length > 0) {
    return mostRecentMatchingRun(artifact, pathMatches, runs)
  }

  const boundedMatches = runs.filter(
    (run) =>
      run.status === "completed" &&
      artifactUpdatedDuringRun(artifact, run) &&
      runHasCompletedMutation(run.id, transcript) &&
      runNamesArtifact(run.id, artifact, transcript),
  )
  return boundedMatches.length === 1 ? boundedMatches[0].id : null
}

function mostRecentMatchingRun(
  artifact: WorkspaceArtifact,
  matchingRunIds: readonly string[],
  runs: readonly ConversationRunAudit[],
) {
  const matchingRuns = runs.filter((run) => matchingRunIds.includes(run.id))
  const timeBoundMatches = matchingRuns.filter((run) =>
    artifactUpdatedDuringRun(artifact, run),
  )
  const candidates = timeBoundMatches.length > 0 ? timeBoundMatches : matchingRuns
  return candidates.reduce<ConversationRunAudit | null>((latest, run) => {
    if (!latest) return run
    return (timestamp(run.completedAt) ?? 0) >=
      (timestamp(latest.completedAt) ?? 0)
      ? run
      : latest
  }, null)?.id ?? null
}

function artifactUpdatedDuringRun(
  artifact: WorkspaceArtifact,
  run: ConversationRunAudit,
) {
  const updatedAt = timestamp(artifact.updatedAt)
  const startedAt = timestamp(run.startedAt)
  const completedAt = timestamp(run.completedAt)
  return (
    updatedAt !== null &&
    startedAt !== null &&
    completedAt !== null &&
    updatedAt >= startedAt &&
    updatedAt <= completedAt
  )
}

function runHasCompletedMutation(
  runId: string,
  transcript: readonly TranscriptBlock[],
) {
  return transcript.some(
    (block) =>
      block.type === "activity_group" &&
      block.runId === runId &&
      block.activities.some(
        (activity) =>
          activity.status === "completed" &&
          MUTATING_TOOL_NAMES.has(activity.name),
      ),
  )
}

function runNamesArtifact(
  runId: string,
  artifact: WorkspaceArtifact,
  transcript: readonly TranscriptBlock[],
) {
  return transcript.some(
    (block) =>
      block.type === "message" &&
      block.role === "assistant" &&
      block.runId === runId &&
      !block.streaming &&
      textNamesArtifact(block.text, artifact),
  )
}

function pathMatchesArtifact(value: string, artifact: WorkspaceArtifact) {
  if (artifact.resource?.kind !== "workspace") return false
  const candidate = normalizePath(value)
  const path = normalizePath(artifact.resource.path)
  const title = normalizePath(artifact.title)
  return (
    candidate === path ||
    candidate.endsWith(`/${path}`) ||
    candidate === title ||
    candidate.endsWith(`/${title}`)
  )
}

function textNamesArtifact(value: string, artifact: WorkspaceArtifact) {
  if (artifact.resource?.kind !== "workspace") return false
  const text = value.toLowerCase()
  const path = normalizePath(artifact.resource.path)
  const title = normalizePath(artifact.title)
  return text.includes(path) || text.includes(title)
}

function normalizePath(value: string) {
  return value.trim().replaceAll("\\", "/").replace(/^\.\//, "").toLowerCase()
}
