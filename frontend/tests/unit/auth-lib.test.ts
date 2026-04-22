import path from "node:path"
import { afterEach, describe, expect, it, vi } from "vitest"

vi.mock("server-only", () => ({}))

async function loadAuthModule() {
  vi.resetModules()
  return import("@/lib/auth")
}

describe("auth library path resolution", () => {
  const originalCwd = process.cwd()
  const frontendRoot = path.resolve(originalCwd)
  const repoRoot = path.join(frontendRoot, "..")

  afterEach(() => {
    process.chdir(originalCwd)
    delete process.env.BIOINFOFLOW_HOME
    delete process.env.BETTER_AUTH_DB_PATH
    delete process.env.BETTER_AUTH_SECRET
    delete process.env.NODE_ENV
  })

  it("maps the legacy frontend better-auth.db default to the shared BIOINFOFLOW_HOME state path", async () => {
    process.chdir(frontendRoot)
    process.env.BETTER_AUTH_DB_PATH = "./better-auth.db"

    const { resolveBetterAuthDbPath } = await loadAuthModule()

    expect(resolveBetterAuthDbPath()).toBe(
      path.join(repoRoot, "data", "state", "auth", "better-auth.db"),
    )
  })

  it("prefers BIOINFOFLOW_HOME when no explicit auth db path is configured", async () => {
    process.chdir(frontendRoot)
    process.env.BIOINFOFLOW_HOME = path.join(repoRoot, "custom-home")

    const { resolveBetterAuthDbPath } = await loadAuthModule()

    expect(resolveBetterAuthDbPath()).toBe(
      path.join(repoRoot, "custom-home", "state", "auth", "better-auth.db"),
    )
  })

  it("requires an explicit BETTER_AUTH_SECRET in production", async () => {
    process.chdir(frontendRoot)
    process.env.NODE_ENV = "production"

    const { resolveBetterAuthSecret } = await loadAuthModule()

    expect(() => resolveBetterAuthSecret()).toThrow(
      "BETTER_AUTH_SECRET must be set in production",
    )
  })
})
