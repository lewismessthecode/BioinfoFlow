import { afterEach, describe, expect, it, vi } from "vitest"

const mockRedirect = vi.fn()
const mockCookies = vi.fn()

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    mockRedirect(url)
    throw new Error(`NEXT_REDIRECT: ${url}`)
  },
}))

vi.mock("next/headers", () => ({
  cookies: () => mockCookies(),
}))

import RootPage from "@/app/page"

afterEach(() => {
  delete process.env.DEPLOY_MODE
  delete process.env.APP_RUNTIME
  mockCookies.mockReset()
  mockRedirect.mockReset()
})

describe("RootPage", () => {
  it("redirects visitors to /auth", async () => {
    mockCookies.mockReturnValue({ get: () => undefined })
    await expect(RootPage()).rejects.toThrow("NEXT_REDIRECT: /auth")
    expect(mockRedirect).toHaveBeenCalledWith("/auth")
  })

  it("renders the demo landing page on / when demo mode is enabled and access is not granted", async () => {
    process.env.DEPLOY_MODE = "demo"
    mockCookies.mockReturnValue({ get: () => undefined })

    const page = await RootPage()

    expect(mockRedirect).not.toHaveBeenCalled()
    expect(page).toBeTruthy()
  })

  it("keeps the demo landing page reachable after guest access is granted", async () => {
    process.env.DEPLOY_MODE = "demo"
    mockCookies.mockReturnValue({
      get: (name: string) =>
        name === "bioinfoflow_demo_access" ? { value: "guest" } : undefined,
    })

    const page = await RootPage()

    expect(mockRedirect).not.toHaveBeenCalled()
    expect(page).toBeTruthy()
  })

  it("renders the demo landing page when APP_RUNTIME is demo", async () => {
    process.env.APP_RUNTIME = "demo"
    mockCookies.mockReturnValue({ get: () => undefined })

    const page = await RootPage()

    expect(mockRedirect).not.toHaveBeenCalled()
    expect(page).toBeTruthy()
  })
})
