import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("layout icon metadata", () => {
  it("publishes versioned png favicon assets for browser tabs and apple icons", () => {
    const source = readFileSync(resolve(process.cwd(), "app/layout.tsx"), "utf8")

    expect(source).toContain('url: `/icon-light-32x32.png?v=${iconVersion}`')
    expect(source).toContain('url: `/icon-dark-32x32.png?v=${iconVersion}`')
    expect(source).toContain('shortcut: `/favicon.ico?v=${iconVersion}`')
    expect(source).toContain('apple: `/apple-icon.png?v=${iconVersion}`')
  })
})
