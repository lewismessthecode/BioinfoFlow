import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("globals.css light theme tokens", () => {
  it("keeps the sidebar neutral while brightening the main shell closer to Codex", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toContain("--background: #fcfcfd;")
    expect(css).toContain("--card: #ffffff;")
    expect(css).toContain("--sidebar: #f4f4f5;")
    expect(css).toContain("--sidebar-accent: #e9e9ee;")
    expect(css).toContain("--surface-subtle: #f6f6f8;")

    expect(css).not.toContain("--background: #f7f7f8;")
    expect(css).not.toContain("--card: #fafafa;")
    expect(css).not.toContain("--sidebar: #f3f3f3;")
    expect(css).not.toContain("--sidebar-accent: #dedee2;")
    expect(css).not.toContain("--surface-subtle: #f1f1f3;")
  })
})
