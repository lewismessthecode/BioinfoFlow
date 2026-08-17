import { describe, expect, it } from "vitest"

import { buildSupplementalArtifactBlocks } from "@/components/bioinfoflow/agent/use-agent-transcript-artifacts"
import type { WorkspaceArtifact } from "@/lib/agent/workspace-adapter"

const baseArtifact: WorkspaceArtifact = {
  id: "workspace:project-1:report.xlsx",
  source: "workspace",
  runId: null,
  title: "report.xlsx",
  summary: null,
  kind: "xlsx",
  mediaType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  sizeBytes: 128,
  createdAt: "2026-08-16T08:00:03.000Z",
  updatedAt: "2026-08-16T08:00:03.000Z",
  payload: null,
  resource: {
    kind: "workspace",
    projectId: "project-1",
    path: "report.xlsx",
  },
}

describe("buildSupplementalArtifactBlocks", () => {
  it("maps workspace deliverables created during the conversation", () => {
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [baseArtifact],
        runs: [
          {
            id: "run-1",
            status: "completed",
            startedAt: "2026-08-16T08:00:00.000Z",
            completedAt: "2026-08-16T08:00:04.000Z",
            executionConfig: null,
          },
        ],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([
      {
        type: "artifact",
        id: "workspace-artifact:workspace:project-1:report.xlsx",
        runId: null,
        createdAt: "2026-08-16T08:00:03.000Z",
        artifactId: "workspace:project-1:report.xlsx",
        title: "report.xlsx",
        mediaType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
      },
    ])
  })

  it("excludes stale workspace files and artifacts already present in the transcript", () => {
    const stale = {
      ...baseArtifact,
      id: "workspace:project-1:stale.html",
      title: "stale.html",
      createdAt: "2026-08-15T08:00:00.000Z",
      updatedAt: "2026-08-15T08:00:00.000Z",
    }
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [stale, baseArtifact],
        runs: [
          {
            id: "run-1",
            status: "completed",
            startedAt: "2026-08-16T08:00:00.000Z",
            completedAt: "2026-08-16T08:00:04.000Z",
            executionConfig: null,
          },
        ],
        transcriptArtifactIds: new Set([baseArtifact.id]),
      }),
    ).toEqual([])
  })
})
