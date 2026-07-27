import { describe, expect, it } from "vitest"

import { classifyActivity } from "@/lib/agent-runtime/activity-groups"
import type { AgentRuntimeToolActivity } from "@/lib/agent-runtime/types"

const activity = (
  name: string,
  argumentsValue: Record<string, unknown> = {},
): AgentRuntimeToolActivity => ({
  id: `activity-${name}`,
  actionId: null,
  callId: `call-${name}`,
  name,
  status: "completed",
  arguments: argumentsValue,
  relatedFiles: [],
  sources: [],
  seqStart: 1,
  seqEnd: 1,
})

describe("classifyActivity", () => {
  it.each([
    ["glob", { pattern: "**/*.wdl" }],
    ["grep", { pattern: "sample" }],
    ["files.read", { path: "workflow.wdl" }],
    ["files__read", { path: "workflow.wdl" }],
    ["files__apply_patch", { operations: [{ op: "create", path: "new.wdl" }] }],
    ["files__write", { path: "workflow.wdl", content: "workflow demo {}" }],
    ["images.build", { dockerfile: "Dockerfile" }],
  ])("uses the generic fallback for retired tool name %s", (name, args) => {
    expect(classifyActivity(activity(name, args))).toBe("other")
  })

  it.each([
    "grep -R sample results/",
    "find workflows -name '*.wdl' -print",
  ])("keeps Bash read-command semantics for %s", (command) => {
    expect(classifyActivity(activity("bash", { command }))).toBe("read")
  })
})
