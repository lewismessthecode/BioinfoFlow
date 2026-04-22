import { describe, expect, it } from "vitest"

import { buildHubWorkflowGroups } from "@/lib/workflow-groups"

describe("workflow-groups", () => {
  it("groups same-name workflows and keeps the latest version as the card representative", () => {
    const groups = buildHubWorkflowGroups([
      {
        id: "wf-old",
        name: "Deaf_20",
        description: "Older",
        source: "local",
        engine: "wdl",
        version: "V2.0.9.9",
      },
      {
        id: "wf-new",
        name: "Deaf_20",
        description: "Latest",
        source: "local",
        engine: "wdl",
        version: "V2.1.0.0",
      },
      {
        id: "wf-other",
        name: "WGS_CLINICAL",
        description: "Other",
        source: "local",
        engine: "wdl",
        version: "3.6.2",
      },
    ])

    expect(groups).toHaveLength(2)
    expect(groups[0]?.latest_workflow.id).toBe("wf-new")
    expect(groups[0]?.versions).toHaveLength(2)
    expect(groups[1]?.latest_workflow.id).toBe("wf-other")
  })
})
