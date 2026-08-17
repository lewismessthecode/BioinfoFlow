import { describe, expect, it } from "vitest"

import { buildSupplementalArtifactBlocks } from "@/components/bioinfoflow/agent/use-agent-transcript-artifacts"
import type {
  ConversationRunAudit,
  TranscriptBlock,
} from "@/lib/agent/conversation-model/types"
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

function assistantMessage(
  runId: string,
  text: string,
  createdAt = "2026-08-16T08:00:09.000Z",
): TranscriptBlock {
  return {
    type: "message",
    id: `assistant:${runId}:${createdAt}`,
    runId,
    createdAt,
    role: "assistant",
    text,
    references: [],
    streaming: false,
  }
}

function completedWrite(runId: string, path: string): TranscriptBlock {
  return {
    type: "activity_group",
    id: `activity:${runId}:${path}`,
    runId,
    createdAt: "2026-08-16T08:00:02.000Z",
    executionMode: "serial",
    activities: [
      {
        id: `write:${path}`,
        callId: `call:${path}`,
        name: "write",
        displayName: "Write",
        category: "write",
        summary: `Write ${path}`,
        status: "completed",
        input: {},
        output: null,
        error: null,
        startedAt: "2026-08-16T08:00:01.000Z",
        completedAt: "2026-08-16T08:00:02.000Z",
        details: [
          {
            id: "path",
            kind: "path",
            label: null,
            value: `/workspace/${path}`,
            format: "path",
            copyable: true,
            truncated: false,
            redacted: false,
          },
        ],
      },
    ],
  }
}

describe("buildSupplementalArtifactBlocks", () => {
  it("does not leak one conversation's workspace artifacts into sibling conversations", () => {
    const artifacts = [
      {
        ...baseArtifact,
        id: "workspace:project-1:samples.tsv",
        title: "samples.tsv",
        resource: {
          kind: "workspace" as const,
          projectId: "project-1",
          path: "samples.tsv",
        },
      },
      {
        ...baseArtifact,
        id: "workspace:project-1:index.html",
        title: "index.html",
        resource: {
          kind: "workspace" as const,
          projectId: "project-1",
          path: "index.html",
        },
      },
      baseArtifact,
    ]
    const unrelatedInput = {
      artifacts,
      runs: [completedRun("run-unrelated")],
      transcript: [assistantMessage("run-unrelated", "No files were created.")],
      transcriptArtifactIds: new Set<string>(),
    }

    expect(buildSupplementalArtifactBlocks(unrelatedInput)).toEqual([])
    expect(
      buildSupplementalArtifactBlocks({
        ...unrelatedInput,
        runs: [completedRun("run-other")],
        transcript: [assistantMessage("run-other", "Still no file output.")],
      }),
    ).toEqual([])
    expect(
      buildSupplementalArtifactBlocks({
        artifacts,
        runs: [completedRun("run-creator")],
        transcript: [
          completedWrite("run-creator", "samples.tsv"),
          completedWrite("run-creator", "index.html"),
          completedWrite("run-creator", "report.xlsx"),
          assistantMessage(
            "run-creator",
            "Created samples.tsv, index.html, and report.xlsx.",
          ),
        ],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([
      expect.objectContaining({ artifactId: artifacts[0].id, runId: "run-creator" }),
      expect.objectContaining({ artifactId: artifacts[1].id, runId: "run-creator" }),
      expect.objectContaining({ artifactId: baseArtifact.id, runId: "run-creator" }),
    ])
  })

  it("keeps an artifact on its creating turn when the same conversation continues", () => {
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
        transcript: [
          completedWrite("run-created", "report.xlsx"),
          assistantMessage("run-created", "Created report.xlsx."),
          assistantMessage(
            "run-later",
            "Answered the follow-up without creating another artifact.",
            "2026-08-16T08:05:09.000Z",
          ),
        ],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([
      expect.objectContaining({
        artifactId: baseArtifact.id,
        runId: "run-created",
      }),
    ])
  })

  it("uses an explicitly named, run-bounded filesystem update for opaque shell output", () => {
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [baseArtifact],
        runs: [
          completedRun(
            "run-shell",
            "2026-08-16T08:00:00",
            "2026-08-16T08:00:10",
          ),
        ],
        transcript: [
          {
            type: "activity_group",
            id: "activity:run-shell",
            runId: "run-shell",
            createdAt: "2026-08-16T08:00:01Z",
            executionMode: "serial",
            activities: [
              {
                id: "bash:generate",
                callId: "call:generate",
                name: "bash",
                displayName: "Bash",
                category: "command",
                summary: "Generate workbook",
                status: "completed",
                input: {},
                output: null,
                error: null,
                startedAt: "2026-08-16T08:00:01Z",
                completedAt: "2026-08-16T08:00:04Z",
              },
            ],
          },
          assistantMessage("run-shell", "Generated report.xlsx."),
        ],
        transcriptArtifactIds: new Set(),
      }),
    ).toEqual([
      expect.objectContaining({
        artifactId: baseArtifact.id,
        runId: "run-shell",
      }),
    ])
  })

  it("excludes unproven workspace files and artifacts already present in the transcript", () => {
    const stale = {
      ...baseArtifact,
      id: "workspace:project-1:stale.html",
      title: "stale.html",
      createdAt: "2026-08-15T08:00:00.000Z",
      updatedAt: "2026-08-15T08:00:00.000Z",
      resource: {
        kind: "workspace" as const,
        projectId: "project-1",
        path: "stale.html",
      },
    }
    expect(
      buildSupplementalArtifactBlocks({
        artifacts: [stale, baseArtifact],
        runs: [completedRun("run-1")],
        transcript: [
          completedWrite("run-1", "report.xlsx"),
          assistantMessage("run-1", "Created report.xlsx."),
        ],
        transcriptArtifactIds: new Set([baseArtifact.id]),
      }),
    ).toEqual([])
  })
})
