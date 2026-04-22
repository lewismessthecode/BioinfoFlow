/**
 * Tests for cookie security attributes — Phase 2 Fix 17.
 */
import { describe, it, expect } from "vitest"
import { setSecureCookie } from "@/lib/cookies"

describe("setSecureCookie", () => {
  it("includes SameSite=Lax attribute", () => {
    const cookie = setSecureCookie("NEXT_LOCALE", "en", { maxAge: 31536000 })
    expect(cookie).toContain("SameSite=Lax")
  })

  it("includes Secure attribute in production", () => {
    const cookie = setSecureCookie("NEXT_LOCALE", "en", {
      maxAge: 31536000,
      secure: true,
    })
    expect(cookie).toContain("Secure")
  })

  it("includes path=/ by default", () => {
    const cookie = setSecureCookie("NEXT_LOCALE", "en", { maxAge: 31536000 })
    expect(cookie).toContain("path=/")
  })

  it("includes max-age when specified", () => {
    const cookie = setSecureCookie("NEXT_LOCALE", "en", { maxAge: 31536000 })
    expect(cookie).toContain("max-age=31536000")
  })

  it("does not include Secure when secure is false", () => {
    const cookie = setSecureCookie("NEXT_LOCALE", "en", {
      maxAge: 31536000,
      secure: false,
    })
    expect(cookie).not.toContain("Secure")
  })

  it("encodes cookie value with special characters", () => {
    const cookie = setSecureCookie("test", "a=b;c", { secure: false })
    expect(cookie).toContain("test=a%3Db%3Bc")
  })
})
