import { readFileSync } from "node:fs"
import { resolve } from "node:path"
import { describe, expect, it } from "vitest"

describe("icon variant assets", () => {
  it("keeps light and dark tab icons as distinct files", () => {
    const light = readFileSync(resolve(process.cwd(), "public/icon-light-32x32.png"))
    const dark = readFileSync(resolve(process.cwd(), "public/icon-dark-32x32.png"))

    expect(Buffer.compare(light, dark)).not.toBe(0)
  })
})
