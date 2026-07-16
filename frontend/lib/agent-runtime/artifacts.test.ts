import { describe, expect, it } from "vitest"

import type { AgentRuntimeArtifact } from "./types"
import * as agentRuntime from "./index"

function artifact(
  type: string,
  overrides: Partial<AgentRuntimeArtifact> = {},
): AgentRuntimeArtifact {
  return {
    id: `${type}-artifact`,
    session_id: "session-1",
    turn_id: "turn-1",
    action_id: null,
    type,
    title: type,
    summary: null,
    payload: null,
    file_path: null,
    resource_ref: null,
    created_at: "2026-06-30T00:00:00Z",
    updated_at: "2026-06-30T00:00:00Z",
    ...overrides,
  }
}

describe("Agent runtime deliverable artifact semantics", () => {
  it("counts only generated file artifacts for review surfaces", () => {
    const { deliverableArtifacts } = agentRuntime as {
      deliverableArtifacts?: (artifacts: AgentRuntimeArtifact[]) => AgentRuntimeArtifact[]
    }

    expect(deliverableArtifacts).toBeTypeOf("function")

    const artifacts = [
      artifact("command"),
      artifact("log_summary"),
      artifact("todo_list"),
      artifact("run", { file_path: "runs/run-1/report.html" }),
      artifact("workflow", { file_path: "workflows/rnaseq/main.nf" }),
      artifact("project", { file_path: "projects/project-1" }),
      artifact("image", { payload: { image: { id: "img-1", name: "ubuntu" } } }),
      artifact("remote_command", { file_path: "/tmp/stdout.txt" }),
      artifact("remote_file", { file_path: "/tmp/remote.txt" }),
      artifact("remote_directory", { file_path: "/tmp/remote-dir" }),
      artifact("unknown", { file_path: "results/table.tsv" }),
      artifact("markdown", { payload: { path: "report.md", content: "# Report" } }),
      artifact("image", { file_path: "plots/pca.png" }),
      artifact("spreadsheet", { resource_ref: { url: "/api/v1/agent/fs/download?path=sheet.xlsx" } }),
    ]

    expect(deliverableArtifacts(artifacts)).toEqual(artifacts.slice(-3))
  })

  it("keeps supported file artifacts in input order", () => {
    const { deliverableArtifacts } = agentRuntime as {
      deliverableArtifacts?: (artifacts: AgentRuntimeArtifact[]) => AgentRuntimeArtifact[]
    }

    expect(deliverableArtifacts).toBeTypeOf("function")

    const artifacts = [
      artifact("html", { payload: { path: "index.html", content: "<h1>Report</h1>" } }),
      artifact("pdf", { file_path: "summary.pdf" }),
      artifact("sheet", { payload: { rows: [["sample", "reads"]] } }),
      artifact("file", { file_path: "notes.txt" }),
    ]

    expect(deliverableArtifacts(artifacts)).toEqual(artifacts)
  })

  it("excludes supported file types without a renderable file source", () => {
    const { deliverableArtifacts } = agentRuntime as {
      deliverableArtifacts?: (artifacts: AgentRuntimeArtifact[]) => AgentRuntimeArtifact[]
    }

    expect(deliverableArtifacts).toBeTypeOf("function")

    expect(deliverableArtifacts([
      artifact("html"),
      artifact("pdf", { payload: {} }),
      artifact("spreadsheet", { resource_ref: {} }),
    ])).toEqual([])
  })
})
