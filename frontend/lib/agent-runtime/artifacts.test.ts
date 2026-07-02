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
  it("counts only deliverable artifacts for review surfaces", () => {
    const { isDeliverableArtifact, countDeliverableArtifacts } = agentRuntime as {
      isDeliverableArtifact?: (artifact: AgentRuntimeArtifact) => boolean
      countDeliverableArtifacts?: (artifacts: AgentRuntimeArtifact[]) => number
    }

    expect(isDeliverableArtifact).toBeTypeOf("function")
    expect(countDeliverableArtifacts).toBeTypeOf("function")

    const artifacts = [
      artifact("command"),
      artifact("log_summary"),
      artifact("todo_list"),
      artifact("markdown"),
      artifact("image"),
      artifact("unknown", { file_path: "results/table.tsv" }),
    ]

    expect(artifacts.map((item) => isDeliverableArtifact(item))).toEqual([
      false,
      false,
      false,
      true,
      true,
      true,
    ])
    expect(countDeliverableArtifacts(artifacts)).toBe(3)
  })
})
