import { describe, expect, it } from "vitest"

describe("vitest setup", () => {
  it("runs in a browser-like environment", () => {
    expect(typeof window).toBe("object")
    expect(typeof document).toBe("object")
  })

  it("provides a functioning DOM", () => {
    const el = document.createElement("div")
    el.textContent = "hello"
    document.body.appendChild(el)
    expect(document.body.textContent).toContain("hello")
    document.body.removeChild(el)
  })

  it("provides localStorage", () => {
    localStorage.setItem("smoke-key", "smoke-value")
    expect(localStorage.getItem("smoke-key")).toBe("smoke-value")
    localStorage.removeItem("smoke-key")
  })

  it("provides a functioning fetch global", () => {
    expect(typeof fetch).toBe("function")
  })
})
