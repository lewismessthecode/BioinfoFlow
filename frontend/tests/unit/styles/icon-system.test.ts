import { readdirSync, readFileSync, statSync } from "node:fs"
import { join, relative } from "node:path"
import { describe, expect, it } from "vitest"

const frontendRoot = join(process.cwd())
const allowedLucideImportFiles = new Set([
  "lib/icons.ts",
])

function collectSourceFiles(dir: string): string[] {
  return readdirSync(dir).flatMap((entry) => {
    const fullPath = join(dir, entry)
    const stat = statSync(fullPath)

    if (stat.isDirectory()) {
      if (["node_modules", ".next", "coverage"].includes(entry)) return []
      return collectSourceFiles(fullPath)
    }

    if (!/\.(ts|tsx)$/.test(entry)) return []
    return [fullPath]
  })
}

describe("icon system boundaries", () => {
  it("routes app glyphs through the local icon adapter", () => {
    const offenders = collectSourceFiles(frontendRoot)
      .map((file) => ({
        file: relative(frontendRoot, file),
        source: readFileSync(file, "utf8"),
      }))
      .filter(({ file, source }) => {
        if (allowedLucideImportFiles.has(file)) return false
        if (file.includes("tests/")) return false
        return /from\s+["']lucide-react["']/.test(source)
      })
      .map(({ file }) => file)

    expect(offenders).toEqual([])
  })

  it("keeps the global lucide stroke and motion rule centralized", () => {
    const globals = readFileSync(join(frontendRoot, "app/globals.css"), "utf8")

    expect(globals).toContain(".lucide")
    expect(globals).toContain('[data-slot="app-icon"]')
    expect(globals).toContain("stroke-width: 1.75")
    expect(globals).toContain("transition-duration: var(--duration-fast)")
  })

  it("keeps button icons on the shared stroke weight", () => {
    const button = readFileSync(join(frontendRoot, "components/ui/button.tsx"), "utf8")

    expect(button).toContain("[&_svg]:stroke-[1.75]")
  })
})
