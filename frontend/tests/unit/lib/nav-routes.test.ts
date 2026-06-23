import { describe, expect, it } from "vitest"

import { NAV_ROUTES } from "@/lib/nav-routes"

describe("NAV_ROUTES", () => {
  it("keeps the top-level navigation in the expected product order", () => {
    expect(NAV_ROUTES.map((route) => route.key)).toEqual([
      "dashboard",
      "agent",
      "workflows",
      "runs",
      "images",
      "connections",
      "scheduler",
      "settings",
    ])
  })

  it("exposes unique route keys and hrefs for every primary destination", () => {
    const keys = NAV_ROUTES.map((route) => route.key)
    const hrefs = NAV_ROUTES.map((route) => route.href)

    expect(new Set(keys).size).toBe(keys.length)
    expect(new Set(hrefs).size).toBe(hrefs.length)
    expect(hrefs).toContain("/agent")
    expect(hrefs).toContain("/runs")
    expect(hrefs).toContain("/connections")
    expect(hrefs).toContain("/settings")
  })
})
