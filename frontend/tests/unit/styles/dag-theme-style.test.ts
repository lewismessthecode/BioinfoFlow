import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("dag theme styling", () => {
  it("routes run-status dots through semantic tokens instead of hardcoded emerald shades", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/dag/dag-header.tsx"),
      "utf8",
    )

    expect(source).not.toContain("bg-emerald-400")
    expect(source).not.toContain("bg-emerald-500")
  })

  it("derives dag ambient chrome from theme tokens instead of a fixed green glow", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/globals.css"),
      "utf8",
    )

    expect(source).toContain("color-mix(in srgb, var(--accent)")
    expect(source).not.toContain("--dag-glow: rgba(16, 185, 129, 0.12);")
    expect(source).not.toContain("--dag-glow: rgba(34, 197, 94, 0.08);")
  })
})
