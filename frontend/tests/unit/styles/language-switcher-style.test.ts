import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("language switcher styling", () => {
  it("matches the compact navbar icon button radius", () => {
    const source = readFileSync(
      resolve(process.cwd(), "components/language-switcher.tsx"),
      "utf8",
    )

    expect(source).toContain("h-8 w-8 rounded-lg")
    expect(source).not.toContain("h-8 w-8 rounded-full")
  })
})
