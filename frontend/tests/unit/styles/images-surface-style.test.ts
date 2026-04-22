import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("images page card styling", () => {
  it("keeps image cards softly separated from the page instead of using bright white lift", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/images/components/image-views.tsx"),
      "utf8"
    )

    expect(source).toContain("bg-card/92")
    expect(source).toContain("hover:shadow-sm")
    expect(source).not.toContain("hover:shadow-lg")
    expect(source).not.toContain("bg-card/70")
  })

  it("uses a softer action button and a quieter warning banner", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/images/page.tsx"),
      "utf8"
    )

    expect(source).toContain("border-warning/24 bg-warning/7")
    expect(source).toContain("bg-card text-foreground shadow-none")
    expect(source).not.toContain("bg-warning/10")
    expect(source).not.toContain("<Button onClick={() => setUploadOpen(true)}>")
  })
})
