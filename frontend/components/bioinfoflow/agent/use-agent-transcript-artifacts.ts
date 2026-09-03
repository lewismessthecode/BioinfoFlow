"use client"

import { useEffect, useMemo, useState } from "react"

import type {
  ArtifactTranscriptBlock,
  ConversationRunAudit,
  ConversationViewModel,
} from "@/lib/agent/conversation-model/types"
import {
  type AgentWorkspaceAdapter,
  type WorkspaceArtifact,
  workspaceArtifactSelectionId,
} from "@/lib/agent/workspace-adapter"

type SupplementalArtifactInput = {
  artifacts: readonly WorkspaceArtifact[]
  runs: readonly ConversationRunAudit[]
  transcriptArtifactIds: ReadonlySet<string>
}

export function buildSupplementalArtifactBlocks({
  artifacts,
  runs,
  transcriptArtifactIds,
}: SupplementalArtifactInput): ArtifactTranscriptBlock[] {
  const runIds = new Set(runs.map((run) => run.id))

  return artifacts
    .flatMap((artifact) => {
      if (artifact.source !== "session" || artifact.resource?.kind === "workspace") {
        return []
      }
      const selectionId = workspaceArtifactSelectionId(artifact)
      if (transcriptArtifactIds.has(selectionId)) return []
      if (!artifact.runId || !runIds.has(artifact.runId)) return []
      return [{ artifact, runId: artifact.runId, selectionId }]
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
