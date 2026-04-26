import { afterEach, describe, expect, it, vi } from "vitest"
import { NextRequest } from "next/server"

function createRequest(path: string, cookies?: Record<string, string>): NextRequest {
  const url = new URL(path, "http://localhost:3000")
  const req = new NextRequest(url)
  if (cookies) {
    for (const [name, value] of Object.entries(cookies)) {
      req.cookies.set(name, value)
    }
  }
  return req
}

async function loadProxyModule() {
  vi.resetModules()
  return import("@/proxy")
}

afterEach(() => {
  delete process.env.AUTH_MODE
  delete process.env.DEPLOY_MODE
  delete process.env.APP_RUNTIME
  vi.resetModules()
})

describe("middleware demo mode", () => {
  it("keeps landing, auth, and demo auth endpoints public", async () => {
    process.env.DEPLOY_MODE = "demo"
    process.env.AUTH_MODE = "dev"

    const { proxy } = await loadProxyModule()
    const allowedPaths = ["/", "/auth", "/api/demo-auth?provider=github"]

    for (const path of allowedPaths) {
      const res = proxy(createRequest(path))
      expect(res.status, `expected ${path} to pass through in demo mode`).toBe(200)
      expect(res.headers.get("location"), `expected ${path} to avoid redirects in demo mode`).toBeNull()
    }
  })

  it("redirects demo app routes to /auth until the demo access cookie exists", async () => {
    process.env.DEPLOY_MODE = "demo"
    process.env.AUTH_MODE = "dev"

    const { proxy } = await loadProxyModule()
    const res = proxy(createRequest("/agent"))

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
  })

  it("allows demo app routes after the demo access cookie is set", async () => {
    process.env.DEPLOY_MODE = "demo"
    process.env.AUTH_MODE = "dev"

    const { proxy } = await loadProxyModule()
    const res = proxy(
      createRequest("/runs/demo-run-1", { bioinfoflow_demo_access: "github" }),
    )

    expect(res.status).toBe(200)
    expect(res.headers.get("location")).toBeNull()
  })

  it("redirects unsupported demo routes back to landing", async () => {
    process.env.DEPLOY_MODE = "demo"
    process.env.AUTH_MODE = "dev"

    const { proxy } = await loadProxyModule()
    const res = proxy(
      createRequest("/settings", { bioinfoflow_demo_access: "github" }),
    )

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get("location")!).pathname).toBe("/")
  })

  it("treats APP_RUNTIME=demo as a demo deployment in the proxy", async () => {
    process.env.APP_RUNTIME = "demo"
    process.env.AUTH_MODE = "dev"

    const { proxy } = await loadProxyModule()
    const res = proxy(createRequest("/agent"))

    expect(res.status).toBe(307)
    expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
  })
})
