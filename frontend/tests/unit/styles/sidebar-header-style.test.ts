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
    expect(source).toContain("hover:bg-sidebar-accent/75")
  })

  it("aligns the sidebar header controls with the compact top navbar row", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/sidebar/sidebar.tsx"),
      "utf8"
    )

    expect(source).toContain('"flex h-11 shrink-0 items-center"')
    expect(source).toContain("h-8 w-8 rounded-[8px]")
    expect(source).toContain("rounded-[8px]")
    expect(source).not.toContain("rounded-full")
  })

  it("keeps the protected app shell on the mobile-safe viewport unit", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/app-layout.tsx"),
      "utf8",
    )

    expect(source).toContain("min-h-[100dvh]")
    expect(source).not.toContain("h-screen")
  })
})
