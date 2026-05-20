import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("globals.css light theme tokens", () => {
  it("keeps the default shell airy with a Gemini-inspired halo palette", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toContain("--background: #fdfdff;")
    expect(css).toContain("--card: #ffffff;")
    expect(css).toContain("--sidebar: #f8f8fa;")
    expect(css).toContain("--sidebar-accent: #eeeeef;")
    expect(css).toContain("--surface-subtle: #f7f8fb;")
    expect(css).toContain("--agent-halo: rgba(163, 210, 246, 0.55);")
    expect(css).toContain("--composer-shadow:")

    expect(css).not.toContain("--background: #fcfcfd;")
    expect(css).not.toContain("--background: #f7f7f8;")
    expect(css).not.toContain("--card: #fafafa;")
    expect(css).not.toContain("--sidebar: #f3f3f3;")
    expect(css).not.toContain("--sidebar-accent: #dedee2;")
    expect(css).not.toContain("--surface-subtle: #f1f1f3;")
  })
})
