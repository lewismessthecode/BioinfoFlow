import { describe, expect, it } from "vitest"
import { NextRequest } from "next/server"

import { GET } from "@/app/api/demo-auth/route"

describe("demo auth route", () => {
  it("starts a demo session for a supported provider", async () => {
    const request = new NextRequest(
      "http://localhost:3000/api/demo-auth?provider=guest&next=%2Fagent",
    )

    const response = await GET(request)

    expect(response.status).toBe(307)
    expect(new URL(response.headers.get("location")!).pathname).toBe("/agent")
    expect(response.cookies.get("bioinfoflow_demo_access")?.value).toBe("guest")
  })

  it("clears the demo session and returns to landing on logout", async () => {
    const request = new NextRequest(
      "http://localhost:3000/api/demo-auth?action=logout&next=%2F",
    )

    const response = await GET(request)

    expect(response.status).toBe(307)
    expect(new URL(response.headers.get("location")!).pathname).toBe("/")
    expect(response.cookies.get("bioinfoflow_demo_access")?.value).toBe("")
    expect(response.cookies.get("bioinfoflow_demo_access")?.maxAge).toBe(0)
  })
})
