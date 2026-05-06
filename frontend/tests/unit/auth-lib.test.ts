import path from "node:path"
import { mkdtempSync, readFileSync, rmSync } from "node:fs"
import { tmpdir } from "node:os"
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
  const tempDirs: string[] = []

  afterEach(() => {
    process.chdir(originalCwd)
    delete process.env.BIOINFOFLOW_HOME
    delete process.env.BETTER_AUTH_DB_PATH
    delete process.env.BETTER_AUTH_SECRET
    delete process.env.BETTER_AUTH_URL
    delete process.env.NODE_ENV
    for (const dir of tempDirs.splice(0)) {
      rmSync(dir, { force: true, recursive: true })
    }
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

  it("creates a persistent local auth secret for localhost production starts", async () => {
    process.chdir(frontendRoot)
    const bioinfoflowHome = mkdtempSync(path.join(tmpdir(), "bioinfoflow-auth-"))
    tempDirs.push(bioinfoflowHome)
    process.env.BIOINFOFLOW_HOME = bioinfoflowHome
    process.env.BETTER_AUTH_URL = "http://localhost:3000"
    process.env.NODE_ENV = "production"

    const { resolveBetterAuthSecret } = await loadAuthModule()

    const firstSecret = resolveBetterAuthSecret()
    const secondSecret = resolveBetterAuthSecret()
    const secretPath = path.join(
      bioinfoflowHome,
      "state",
      "auth",
      ".better-auth-local-secret",
    )

    expect(firstSecret).toHaveLength(44)
    expect(secondSecret).toBe(firstSecret)
    expect(readFileSync(secretPath, "utf8").trim()).toBe(firstSecret)
  })

  it("requires an explicit BETTER_AUTH_SECRET in production for non-local auth URLs", async () => {
    process.chdir(frontendRoot)
    process.env.BETTER_AUTH_URL = "https://bioinfoflow.example.com"
    process.env.NODE_ENV = "production"

    const { resolveBetterAuthSecret } = await loadAuthModule()

    expect(() => resolveBetterAuthSecret()).toThrow(
      "BETTER_AUTH_SECRET must be set in production",
    )
  })
})
