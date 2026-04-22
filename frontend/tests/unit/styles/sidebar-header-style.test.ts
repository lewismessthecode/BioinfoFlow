import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("sidebar header styling", () => {
  it("avoids a hard white logo tile in dark mode", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/sidebar/sidebar.tsx"),
      "utf8"
    )

    expect(source).toContain("dark:bg-white/5")
    expect(source).not.toContain("bg-white text-sidebar-foreground")
  })
})
