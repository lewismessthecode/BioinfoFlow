import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("Shiki dual-theme syntax colors", () => {
  it("switches generated code tokens to the dark palette in dark mode", () => {
    const css = readFileSync(resolve(process.cwd(), "app/globals.css"), "utf8")

    expect(css).toMatch(
      /\.markdown-code-highlight \.shiki,\s*\.markdown-code-highlight \.shiki span\s*\{[^}]*color:\s*var\(--shiki-light\)\s*!important;/s,
    )
    expect(css).toMatch(
      /\.dark \.markdown-code-highlight \.shiki,\s*\.dark \.markdown-code-highlight \.shiki span\s*\{[^}]*color:\s*var\(--shiki-dark\)\s*!important;/s,
    )
  })
})
