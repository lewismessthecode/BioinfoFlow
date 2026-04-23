import { describe, expect, it, vi } from "vitest"

const mockRedirect = vi.fn()

vi.mock("next/navigation", () => ({
  redirect: (url: string) => {
    mockRedirect(url)
    throw new Error(`NEXT_REDIRECT: ${url}`)
  },
}))

import RootPage from "@/app/page"

describe("RootPage", () => {
  it("redirects visitors to /auth", () => {
    expect(() => RootPage()).toThrow("NEXT_REDIRECT: /auth")
    expect(mockRedirect).toHaveBeenCalledWith("/auth")
  })
})
