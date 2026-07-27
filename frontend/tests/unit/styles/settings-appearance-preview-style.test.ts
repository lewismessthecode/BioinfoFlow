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

  it("uses a compact preview skeleton without terminal decoration", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/settings/settings-page-client.tsx"),
      "utf8"
    )

    expect(source).toContain('className="relative flex min-h-[236px] flex-col')
    expect(source).toContain('data-testid="appearance-preview-main"')
    expect(source).not.toContain("min-h-[420px]")
    expect(source).not.toContain('tokens["terminal-background"]')
  })
})
