// @vitest-environment node

import { describe, expect, it, vi } from "vitest"

import { ensureBetterSqliteNodeAbi } from "@/scripts/better-sqlite3-node-abi.mjs"

function createAbiMismatchError() {
  return new Error(
    "The module '/tmp/better_sqlite3.node' was compiled against a different Node.js version using NODE_MODULE_VERSION 127.",
  )
}

describe("ensureBetterSqliteNodeAbi", () => {
  it("rebuilds when the package import succeeds but the first database open hits an ABI mismatch", async () => {
    let rebuilt = false
    const rebuild = vi.fn(() => {
      rebuilt = true
      return { status: 0 }
    })

    const loadModule = vi.fn(() => {
      return class FakeDatabase {
        constructor() {
          if (!rebuilt) {
            throw createAbiMismatchError()
          }
        }

        close() {}
      }
    })

    const result = await ensureBetterSqliteNodeAbi({
      loadModule,
      rebuild,
      log: {
        warn: vi.fn(),
        error: vi.fn(),
        log: vi.fn(),
      },
    })

    expect(rebuild).toHaveBeenCalledTimes(1)
    expect(result).toEqual({ action: "rebuilt" })
    expect(loadModule).toHaveBeenCalledTimes(2)
  })
})
