import { describe, expect, it } from "vitest"

import { buildSupplementalArtifactBlocks } from "@/components/bioinfoflow/agent/use-agent-transcript-artifacts"
import type {
  ConversationRunAudit,
} from "@/lib/agent/conversation-model/types"
import type { WorkspaceArtifact } from "@/lib/agent/workspace-adapter"

const baseArtifact: WorkspaceArtifact = {
  id: "session:artifact-report",
  source: "session",
  runId: "run-created",
  title: "report.xlsx",
  summary: null,
  kind: "xlsx",
  mediaType: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  sizeBytes: 128,
  createdAt: "2026-08-16T08:00:03.000Z",
  updatedAt: "2026-08-16T08:00:03.000Z",
  payload: null,
  resource: {
    kind: "session",
    artifactId: "artifact-report",
  },
}

function completedRun(
  id: string,
  startedAt = "2026-08-16T08:00:00.000Z",
  completedAt = "2026-08-16T08:00:10.000Z",
): ConversationRunAudit {
  return {
    id,
    status: "completed",
    startedAt,
    completedAt,
    executionConfig: null,
  }
}

describe("buildSupplementalArtifactBlocks", () => {
  it("places a server artifact only on its explicit creating run", () => {
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [baseArtifact],
        runs: [
          completedRun("run-created"),
          completedRun(
            "run-later",
            "2026-08-16T08:05:00.000Z",
            "2026-08-16T08:05:10.000Z",
          ),
        ],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([
      expect.objectContaining({
        artifactId: "artifact-report",
        runId: "run-created",
      }),
    ])
  })

  it("rejects workspace discoveries and server artifacts without an explicit run", () => {
    const workspaceArtifact: WorkspaceArtifact = {
      ...baseArtifact,
      id: "workspace:project-1:report.xlsx",
      source: "workspace",
      runId: "run-created",
      resource: {
        kind: "workspace",
        projectId: "project-1",
        path: "report.xlsx",
      },
    }
    const unscopedServerArtifact: WorkspaceArtifact = {
      ...baseArtifact,
      id: "session:artifact-unscoped",
      runId: null,
      resource: { kind: "session", artifactId: "artifact-unscoped" },
    }

    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [workspaceArtifact, unscopedServerArtifact],
        runs: [completedRun("run-created")],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([])
  })

  it("rejects server artifacts scoped to an unknown run and existing transcript refs", () => {
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [
          { ...baseArtifact, runId: "run-missing" },
          baseArtifact,
        ],
        runs: [completedRun("run-1")],
        transcriptArtifactIds: new Set(["artifact-report"]),
      }),
    ).toEqual([])
  })
})
