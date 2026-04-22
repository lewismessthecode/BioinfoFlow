import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("auth page branding", () => {
  it("reuses the shared Logo component instead of a hard-coded B tile", () => {
    const source = readFileSync(resolve(process.cwd(), "app/auth/page.tsx"), "utf8")

    expect(source).toContain('import { Logo } from "@/components/bioinfoflow/logo"')
    expect(source).toContain("<Logo")
    expect(source).not.toContain(">B<")
  })
})
