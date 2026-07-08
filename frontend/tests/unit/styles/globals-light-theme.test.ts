import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("globals.css theme tokens", () => {
  it("keeps the default shell Notion-neutral, quiet, and low contrast", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toContain("--background: #ffffff;")
    expect(css).toContain("--card: #ffffff;")
    expect(css).toContain("--sidebar: #fbfbfa;")
    expect(css).toContain("--sidebar-accent: #f1f1ef;")
    expect(css).toContain("--surface-subtle: #fbfbfa;")
    expect(css).toContain(
      "--agent-halo: color-mix(in srgb, var(--foreground) 4.5%, transparent);",
    )
    expect(css).toContain(
      "--agent-halo-soft: color-mix(in srgb, var(--accent) 56%, transparent);",
    )
    expect(css).toContain("--agent-halo-opacity: 0.72;")
    expect(css).toContain(
      "--composer-shadow: 0 1px 2px rgba(15, 15, 15, 0.032), 0 10px 24px rgba(15, 15, 15, 0.028);",
    )
    expect(css).toContain(
      '--font-sans: "Geist Sans", "SF Pro Display", "Helvetica Neue", system-ui',
    )

    expect(css).not.toContain("--background: #fbfbfa;")
    expect(css).not.toContain("--sidebar: #f1f0ed;")
    expect(css).not.toContain("--sidebar-accent: #e4e1dc;")
    expect(css).not.toContain("--agent-halo: rgba(227, 222, 215, 0.74);")
    expect(css).not.toContain("--agent-halo: rgba(74, 144, 226, 0.22);")
  })

  it("keeps the dark composer aura neutral and restrained", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toContain(
      "--agent-halo: color-mix(in srgb, var(--foreground) 5.5%, transparent);",
    )
    expect(css).toContain(
      "--agent-halo-soft: color-mix(in srgb, var(--accent) 34%, transparent);",
    )
    expect(css).toContain("--agent-halo-opacity: 0.86;")
    expect(css).toContain(
      "--composer-shadow: 0 1px 2px rgba(0, 0, 0, 0.22), 0 14px 38px rgba(0, 0, 0, 0.20);",
    )
    expect(css).not.toContain("--agent-halo-soft: rgba(27, 38, 59, 0.72);")
    expect(css).not.toContain(
      "--composer-shadow: 0 2px 10px rgba(0, 0, 0, 0.28), 0 18px 48px rgba(0, 0, 0, 0.30);",
    )
  })
})
