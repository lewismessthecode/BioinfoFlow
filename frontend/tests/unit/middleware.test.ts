import { describe, expect, it } from "vitest"
import { NextRequest } from "next/server"

import { proxy, config } from "@/proxy"

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

describe("middleware", () => {
  it("passes through protected routes when auth is disabled", () => {
    process.env.AUTH_ENABLED = "false"
    const req = createRequest("/dashboard")
    const res = proxy(req)
    expect(res.status).toBe(200)
    delete process.env.AUTH_ENABLED
  })

  describe("unauthenticated requests", () => {
    it("redirects /dashboard to /auth when no session cookie", () => {
      process.env.AUTH_ENABLED = "true"
      const req = createRequest("/dashboard")
      const res = proxy(req)
      expect(res.status).toBe(307)
      expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
      delete process.env.AUTH_ENABLED
    })

    it("redirects /agent to /auth when no session cookie", () => {
      process.env.AUTH_ENABLED = "true"
      const req = createRequest("/agent")
      const res = proxy(req)
      expect(res.status).toBe(307)
      expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
      delete process.env.AUTH_ENABLED
    })

    it("redirects /runs to /auth when no session cookie", () => {
      process.env.AUTH_ENABLED = "true"
      const req = createRequest("/runs")
      const res = proxy(req)
      expect(res.status).toBe(307)
      expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
      delete process.env.AUTH_ENABLED
    })
  })

  describe("authenticated requests", () => {
    it("passes through when session cookie is present", () => {
      process.env.AUTH_ENABLED = "true"
      const req = createRequest("/dashboard", { "better-auth.session_token": "valid-token" })
      const res = proxy(req)
      expect(res.status).toBe(200)
      expect(res.headers.get("location")).toBeNull()
      delete process.env.AUTH_ENABLED
    })
  })

  describe("public paths (no redirect)", () => {
    it("passes through / without cookie", () => {
      const req = createRequest("/")
      const res = proxy(req)
      expect(res.status).toBe(200)
    })

    it("passes through /auth without cookie", () => {
      const req = createRequest("/auth")
      const res = proxy(req)
      expect(res.status).toBe(200)
    })

    it("passes through /api/auth routes without cookie", () => {
      const req = createRequest("/api/auth/callback/github")
      const res = proxy(req)
      expect(res.status).toBe(200)
    })

    it("redirects /api/v1 routes without cookie", () => {
      const req = createRequest("/api/v1/projects")
      const res = proxy(req)
      expect(res.status).toBe(307)
      expect(new URL(res.headers.get("location")!).pathname).toBe("/auth")
    })
  })

  describe("matcher config", () => {
    it("has a matcher that excludes static files and _next", () => {
      expect(config.matcher).toBeDefined()
      expect(config.matcher.length).toBeGreaterThan(0)
      // The regex should NOT match _next or files with extensions
      const pattern = new RegExp(config.matcher[0])
      expect(pattern.test("/_next/static/chunk.js")).toBe(false)
      expect(pattern.test("/favicon.ico")).toBe(false)
    })
  })
})
