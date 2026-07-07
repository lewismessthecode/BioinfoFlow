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
    expect(source).toContain("hover:bg-sidebar-foreground/[0.055]")
    expect(source).not.toContain("bg-sidebar-accent")
  })

  it("aligns the sidebar header controls with the compact top navbar row", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/sidebar/sidebar.tsx"),
      "utf8"
    )
    const headerSource = source.slice(
      source.indexOf("<aside"),
      source.indexOf("{!collapsed ? ("),
    )

    expect(headerSource).toContain('"flex h-11 shrink-0 items-center"')
    expect(headerSource).toContain("h-8 w-8 rounded-[8px]")
    expect(headerSource).toContain("rounded-[8px]")
    expect(headerSource).not.toContain("rounded-full")
  })

  it("keeps the workspace section label readable on the warm sidebar", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/bioinfoflow/sidebar/sidebar.tsx"),
      "utf8",
    )

    expect(source).toContain("text-sidebar-foreground/68")
    expect(source).not.toContain("text-sidebar-foreground/52")
  })

  it("keeps the protected app shell on the mobile-safe viewport unit", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/app-layout.tsx"),
      "utf8",
    )

    expect(source).toContain("min-h-[100dvh]")
    expect(source).not.toContain("h-screen")
  })

  it("keeps a fixed desktop sidebar surface while reserving layout width", () => {
    const source = readFileSync(
      resolve(process.cwd(), "app/(app)/app-layout.tsx"),
      "utf8",
    )

    expect(source).toContain(
      'className="relative flex-shrink-0 transition-[width,opacity] duration-200"',
    )
    expect(source).toContain(
      'className="fixed inset-y-0 left-0 z-20 h-[100dvh] transition-[width,opacity] duration-200"',
    )
    expect(source).toContain(
      "style={{ opacity: 1, width: effectiveLeftWidth }}",
    )
  })
})
