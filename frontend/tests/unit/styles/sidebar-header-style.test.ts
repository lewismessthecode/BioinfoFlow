import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("sidebar header styling", () => {
  it("avoids a hard white logo tile and button shell in the sidebar header", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/sidebar/sidebar.tsx"),
      "utf8"
    )

    expect(source).not.toContain("bg-white/80")
    expect(source).not.toContain("bg-white/90")
    expect(source).toContain("bg-sidebar-accent/55")
  })
})
