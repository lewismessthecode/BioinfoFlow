// @vitest-environment node

import { describe, expect, it, vi } from "vitest"

import { ensureBetterSqliteNodeAbi } from "@/scripts/better-sqlite3-node-abi.mjs"

function createAbiMismatchError() {
  return new Error(
    "The module '/tmp/better_sqlite3.node' was compiled against a different Node.js version using NODE_MODULE_VERSION 127.",
  )
}

function createMissingBindingError() {
  const error = new Error(
    [
      "Could not locate the bindings file. Tried:",
      " -> /tmp/node_modules/better-sqlite3/build/better_sqlite3.node",
      " -> /tmp/node_modules/better-sqlite3/lib/binding/node-v127-darwin-arm64/better_sqlite3.node",
    ].join("\n"),
  )

  return Object.assign(error, {
    tries: [
      "/tmp/node_modules/better-sqlite3/build/better_sqlite3.node",
      "/tmp/node_modules/better-sqlite3/lib/binding/node-v127-darwin-arm64/better_sqlite3.node",
    ],
  })
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

  it("rebuilds when the native binding is missing", async () => {
    let rebuilt = false
    const rebuild = vi.fn(() => {
      rebuilt = true
      return { status: 0 }
    })

    const loadModule = vi.fn(() => {
      if (!rebuilt) {
        throw createMissingBindingError()
      }

      return class FakeDatabase {
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
