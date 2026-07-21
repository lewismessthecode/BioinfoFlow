import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("workflow source diff styling", () => {
  it("avoids table-like diff cell borders", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/workflows/[id]/components/workflow-source-tab.tsx"),
      "utf8",
    )

    expect(source).not.toContain("border-r border-border/50")
    expect(source).not.toContain("border-b border-border/60")
    expect(source).toContain("bg-error-muted")
    expect(source).toContain("bg-success-muted")
  })
})
