// @vitest-environment node

import { describe, expect, it } from "vitest"

import {
  buildStartupSummary,
  formatStartupSummary,
  redactSecret,
} from "@/scripts/with-root-env.mjs"

describe("with-root-env startup summary", () => {
  it("prints operational frontend config without leaking secrets", () => {
    const summary = buildStartupSummary({
      command: "dev",
      args: ["--hostname", "0.0.0.0", "--port", "5173"],
      frontendDir: "/repo/frontend",
      repoRoot: "/repo",
      nextBin: "/repo/frontend/node_modules/next/dist/bin/next",
      loadedEnvFiles: [
        { path: "/repo/.env", exists: true },
        { path: "/repo/frontend/.env.local", exists: false },
      ],
      env: {
        NODE_ENV: "development",
        NEXT_PUBLIC_API_BASE_URL: "http://localhost:8000/api/v1",
        NEXT_PUBLIC_AUTH_MODE: "personal",
        NEXT_PUBLIC_AUTH_LOCAL_ENABLED: "true",
        NEXT_PUBLIC_AUTH_SELF_SIGNUP_ENABLED: "false",
        BETTER_AUTH_URL: "http://localhost:5173",
        BETTER_AUTH_SECRET: "super-secret",
        BIOINFOFLOW_HOME: "/srv/bioinfoflow",
      },
      versions: { node: "v22.0.0" },
    })

    expect(summary.command).toBe("dev")
    expect(summary.network).toEqual({
      hostname: "0.0.0.0",
      port: "5173",
      api_base_url: "http://localhost:8000/api/v1",
      better_auth_url: "http://localhost:5173",
    })
    expect(summary.auth).toEqual({
      mode: "personal",
      local_enabled: "true",
      self_signup_enabled: "false",
      better_auth_secret: "set",
    })
    expect(summary.env_files).toEqual([
      { path: "/repo/.env", exists: true },
      { path: "/repo/frontend/.env.local", exists: false },
    ])
    expect(formatStartupSummary(summary)).not.toContain("super-secret")
  })

  it("redacts secret-like values by presence", () => {
    expect(redactSecret("abc123")).toBe("set")
    expect(redactSecret("")).toBe("unset")
    expect(redactSecret(undefined)).toBe("unset")
  })
})
