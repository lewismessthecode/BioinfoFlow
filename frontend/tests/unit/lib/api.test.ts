import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import { ApiError, apiRequest, buildApiUrl, buildWebSocketUrl } from "@/lib/api"

describe("buildApiUrl", () => {
  it("omits empty params and keeps falsey values that matter", () => {
    const url = new URL(
      buildApiUrl("/projects", {
        limit: 20,
        search: "",
        active: false,
        page: 0,
        ignored: null,
        skipped: undefined,
      })
    )

    expect(url.pathname).toBe("/api/v1/projects")
    expect(url.searchParams.get("limit")).toBe("20")
    expect(url.searchParams.get("active")).toBe("false")
    expect(url.searchParams.get("page")).toBe("0")
    expect(url.searchParams.has("search")).toBe(false)
    expect(url.searchParams.has("ignored")).toBe(false)
    expect(url.searchParams.has("skipped")).toBe(false)
  })
})

describe("buildWebSocketUrl", () => {
  it("converts the configured API base URL into a websocket URL", () => {
    const url = new URL(
      buildWebSocketUrl("/terminal/sessions/session-1/ws", {
        project_id: "project-1",
      })
    )

    expect(url.protocol).toBe("ws:")
    expect(url.pathname).toBe("/api/v1/terminal/sessions/session-1/ws")
    expect(url.searchParams.get("project_id")).toBe("project-1")
  })
})

describe("apiRequest", () => {
  const fetchMock = vi.fn<typeof fetch>()

  beforeEach(() => {
    vi.stubGlobal("fetch", fetchMock)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it("sends JSON requests with a content-type header", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          success: true,
          data: [{ id: "p1" }],
          meta: { request_id: "req-1", timestamp: "2026-03-16T00:00:00Z" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )

    const result = await apiRequest<Array<{ id: string }>>("/projects", {
      method: "POST",
      body: JSON.stringify({ name: "Genome" }),
    })

    expect(result.data).toEqual([{ id: "p1" }])
    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/projects",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ name: "Genome" }),
        headers: expect.objectContaining({
          "Content-Type": "application/json",
        }),
      })
    )
  })

  it("does not force a JSON content-type for FormData bodies", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          success: true,
          data: { ok: true },
          meta: { request_id: "req-2", timestamp: "2026-03-16T00:00:00Z" },
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    )

    const formData = new FormData()
    formData.set("file", new Blob(["reads"]), "reads.fastq.gz")

    await apiRequest<{ ok: boolean }>("/files/upload", {
      method: "POST",
      body: formData,
    })

    expect(fetchMock).toHaveBeenCalledWith(
      "http://localhost:8000/api/v1/files/upload",
      expect.objectContaining({
        method: "POST",
        body: formData,
        headers: {},
      })
    )
  })

  it("returns null data for 204 responses", async () => {
    fetchMock.mockResolvedValueOnce(new Response(null, { status: 204 }))

    const result = await apiRequest<null>("/projects/project-1", {
      method: "DELETE",
    })

    expect(result).toEqual({ data: null, meta: undefined })
  })

  it("throws a structured ApiError for error envelopes", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response(
        JSON.stringify({
          success: false,
          error: {
            code: "project_not_found",
            message: "Project missing",
            details: { project_id: "p404" },
          },
          meta: { request_id: "req-3", timestamp: "2026-03-16T00:00:00Z" },
        }),
        { status: 404, statusText: "Not Found", headers: { "Content-Type": "application/json" } }
      )
    )

    await expect(apiRequest("/projects/p404")).rejects.toMatchObject({
      name: "ApiError",
      message: "Project missing",
      code: "project_not_found",
      status: 404,
      details: { project_id: "p404" },
    })
  })

  it("throws when the backend returns invalid JSON", async () => {
    fetchMock.mockResolvedValueOnce(
      new Response("not-json", {
        status: 200,
        headers: { "Content-Type": "application/json" },
      })
    )

    const request = apiRequest("/projects")

    await expect(request).rejects.toBeInstanceOf(ApiError)
    await expect(request).rejects.toMatchObject({
      message: "Invalid JSON response",
      status: 200,
    })
  })
})
