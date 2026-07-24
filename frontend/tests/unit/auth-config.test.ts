import { afterEach, describe, expect, it, vi } from "vitest"

async function loadConfigModule() {
  vi.resetModules()
  return import("@/lib/auth-config")
}

describe("auth config", () => {
  afterEach(() => {
    delete process.env.AUTH_MODE
    delete process.env.AUTH_ENABLED
    delete process.env.NEXT_PUBLIC_AUTH_ENABLED
    delete process.env.NEXT_PUBLIC_AUTH_MODE
  })

  it("defaults to dev mode when auth configuration is absent", async () => {
    const { clientAuthConfig, getServerAuthConfig } = await loadConfigModule()

    expect(getServerAuthConfig().mode).toBe("dev")
    expect(getServerAuthConfig().authEnabled).toBe(false)
    expect(clientAuthConfig.mode).toBe("dev")
    expect(clientAuthConfig.authEnabled).toBe(false)
  })

  it("defaults to personal mode when auth is enabled", async () => {
    process.env.AUTH_ENABLED = "true"

    const { getServerAuthConfig } = await loadConfigModule()

    expect(getServerAuthConfig().mode).toBe("personal")
  })

  it("maps legacy auth_enabled=false to dev mode when auth_mode is unset", async () => {
    process.env.AUTH_ENABLED = "false"

    const { getServerAuthConfig } = await loadConfigModule()

    const config = getServerAuthConfig()
    expect(config.mode).toBe("dev")
    expect(config.authEnabled).toBe(false)
  })

  it("prefers explicit auth_mode over legacy auth_enabled", async () => {
    process.env.AUTH_MODE = "team"
    process.env.AUTH_ENABLED = "false"

    const { getServerAuthConfig } = await loadConfigModule()

    const config = getServerAuthConfig()
    expect(config.mode).toBe("team")
    expect(config.authEnabled).toBe(true)
  })

  it("rejects an invalid server auth mode instead of disabling auth", async () => {
    process.env.AUTH_MODE = "personl"

    await expect(loadConfigModule()).rejects.toThrow(
      "AUTH_MODE must be one of: personal, team, dev",
    )
  })

  it("rejects an invalid public auth mode during module startup", async () => {
    process.env.NEXT_PUBLIC_AUTH_MODE = "personl"

    await expect(loadConfigModule()).rejects.toThrow(
      "AUTH_MODE must be one of: personal, team, dev",
    )
  })
})
