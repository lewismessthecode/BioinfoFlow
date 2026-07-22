import { afterEach, describe, expect, it, vi } from "vitest"

import { GET } from "@/app/runtime-config.js/route"
import {
  serializePublicRuntimeConfig,
} from "@/lib/runtime/public-config"

describe("public runtime configuration", () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it("serializes the public API URL without allowing script termination", () => {
    const script = serializePublicRuntimeConfig({
      apiBaseUrl: "http://localhost:8100/api/v1</script><script>alert(1)</script>",
    })

    expect(script).toContain("http://localhost:8100/api/v1")
    expect(script).not.toContain("</script>")
    expect(script).toContain("\\u003c/script>")
  })

  it("serves the runtime backend URL without caching", async () => {
    vi.stubEnv(
      "BIOINFOFLOW_PUBLIC_API_BASE_URL",
      "http://localhost:8100/api/v1",
    )

    const response = GET()

    expect(response.headers.get("content-type")).toContain("text/javascript")
    expect(response.headers.get("cache-control")).toBe("no-store")
    await expect(response.text()).resolves.toContain(
      '"apiBaseUrl":"http://localhost:8100/api/v1"',
    )
  })
})
