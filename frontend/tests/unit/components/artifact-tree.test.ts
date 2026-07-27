import { describe, expect, it } from "vitest"

import { buildArtifactTree } from "@/components/bioinfoflow/agent-runtime/artifact-tree"
import type { AgentRuntimeArtifact } from "@/lib/agent-runtime"

function artifact(
  id: string,
  path: string | null,
  updatedAt = "2026-07-27T00:00:00Z",
): AgentRuntimeArtifact {
  return {
    id,
    session_id: "session-1",
    turn_id: "turn-1",
    type: "file",
    title: path ?? id,
    summary: `${id} summary`,
    payload: null,
    file_path: path,
    resource_ref: null,
    created_at: updatedAt,
    updated_at: updatedAt,
  }
}

describe("buildArtifactTree", () => {
  it("trims the shared absolute prefix and nests relative directories", () => {
    const tree = buildArtifactTree([
      artifact(
        "workflow",
        "/Users/lewisliu/Dev/ACTIVE/BioinfoFlow/data/projects/run-1/fasta-analysis/workflow.json",
      ),
      artifact(
        "report",
        "/Users/lewisliu/Dev/ACTIVE/BioinfoFlow/data/projects/run-1/fasta-analysis/results/report.md",
      ),
    ])

    expect(tree.root.name).toBe("fasta-analysis")
    expect(tree.root.children.map((node) => node.name)).toEqual([
      "results",
      "workflow.json",
    ])
    expect(tree.fileCount).toBe(2)
    expect(tree.root.path).toBe("fasta-analysis")
  })

  it("keeps the newest record when the same file is produced repeatedly", () => {
    const tree = buildArtifactTree([
      artifact("old", "/workspace/results/report.md", "2026-07-27T01:00:00Z"),
      artifact("new", "/workspace/results/report.md", "2026-07-27T02:00:00Z"),
    ])

    expect(tree.fileCount).toBe(1)
    expect(tree.root.children[0]).toMatchObject({
      kind: "file",
      artifactId: "new",
      name: "report.md",
    })
  })

  it("places a pathless deliverable at the root using its title", () => {
    const tree = buildArtifactTree(
      [
        {
          ...artifact("sheet", null),
          type: "spreadsheet",
          title: "summary.xlsx",
        },
      ],
      "Artifacts",
    )

    expect(tree.root.name).toBe("Artifacts")
    expect(tree.root.children[0]).toMatchObject({
      kind: "file",
      name: "summary.xlsx",
    })
  })

  it("keeps duplicate basenames distinct in separate directories", () => {
    const tree = buildArtifactTree([
      artifact("first", "/workspace/results/report.md"),
      artifact("second", "/workspace/references/report.md"),
    ])

    expect(tree.fileCount).toBe(2)
    expect(tree.root.children.map((node) => node.name)).toEqual([
      "references",
      "results",
    ])
  })
})
