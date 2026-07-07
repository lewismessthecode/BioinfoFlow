import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("globals.css light theme tokens", () => {
  it("keeps the default shell warm, quiet, and low contrast", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toContain("--background: #fbfbfa;")
    expect(css).toContain("--card: #ffffff;")
    expect(css).toContain("--sidebar: #f1f0ed;")
    expect(css).toContain("--sidebar-accent: #e4e1dc;")
    expect(css).toContain("--surface-subtle: #f6f5f2;")
    expect(css).toContain("--agent-halo: rgba(227, 222, 215, 0.74);")
    expect(css).toContain(
      "--composer-shadow: 0 1px 2px rgba(36, 35, 33, 0.04), 0 16px 38px rgba(36, 35, 33, 0.055);",
    )
    expect(css).toContain(
      '--font-sans: "Geist Sans", "SF Pro Display", "Helvetica Neue", system-ui',
    )

    expect(css).not.toContain("--background: #fdfdff;")
    expect(css).not.toContain("--background: #fcfcfd;")
    expect(css).not.toContain("--background: #f7f7f8;")
    expect(css).not.toContain("--card: #fafafa;")
    expect(css).not.toContain("--sidebar: #f8f8fa;")
    expect(css).not.toContain("--sidebar-accent: #eeeeef;")
    expect(css).not.toContain("--agent-halo: rgba(163, 210, 246, 0.55);")
  })
})
