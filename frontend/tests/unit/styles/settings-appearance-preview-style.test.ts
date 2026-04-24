import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("settings appearance preview styling", () => {
  it("keeps the preview shell layout stable without viewport-only inner breakpoints", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/settings/settings-page-client.tsx"),
      "utf8"
    )

    expect(source).not.toContain("xl:grid-cols-[minmax(0,1.1fr)_minmax(180px,0.9fr)]")
    expect(source).toContain("data-testid=\"appearance-preview-main\"")
  })

  it("uses block-level preview skeleton pills instead of empty inline spans", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/settings/settings-page-client.tsx"),
      "utf8"
    )

    expect(source).toContain("className=\"block h-6 w-12 rounded-full\"")
    expect(source).toContain("className=\"block h-7 w-16 rounded-full\"")
  })
})
