import { describe, expect, it } from "vitest"

import { buildSplitDiffRows, buildWorkflowSourceDiff } from "@/lib/workflow-source-diff"

describe("workflow-source-diff", () => {
  it("marks unchanged, removed, and added lines between workflow versions", () => {
    const previous = [
      "version 1.0",
      "workflow Demo {",
      "  call PREP",
      "}",
    ].join("\n")
    const current = [
      "version 1.0",
      "workflow Demo {",
      "  call PREP",
      "  call RESULT",
      "}",
    ].join("\n")

    const diff = buildWorkflowSourceDiff(previous, current)

    expect(diff.summary).toEqual({
      additions: 1,
      deletions: 0,
      changes: 1,
    })
    expect(diff.rows.map((row) => row.type)).toEqual([
      "context",
      "context",
      "context",
      "add",
      "context",
    ])
    expect(diff.rows[3]).toMatchObject({
      type: "add",
      currentLineNumber: 4,
      text: "  call RESULT",
    })
  })

  it("builds split rows that preserve left and right line numbers", () => {
    const diff = buildWorkflowSourceDiff("a\nb\nc", "a\nc\nd")
    const rows = buildSplitDiffRows(diff.rows)

    expect(rows.map((row) => row.type)).toEqual([
      "context",
      "remove",
      "context",
      "add",
    ])
    expect(rows[1].left).toMatchObject({ lineNumber: 2, text: "b" })
    expect(rows[1].right).toBeNull()
    expect(rows[3].left).toBeNull()
    expect(rows[3].right).toMatchObject({ lineNumber: 3, text: "d" })
  })
})
