import { act, renderHook, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

const { apiRequestMock } = vi.hoisted(() => ({
  apiRequestMock: vi.fn(),
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => apiRequestMock(...args),
  }
})

import { useLlmCatalog } from "@/hooks/use-llm-catalog"

const emptyConfiguration = {
  summary: {
    provider_count: 0,
    configured_provider_count: 0,
    available_provider_count: 0,
    model_count: 0,
    profile_count: 0,
  },
  providers: [],
  models: [],
  profiles: [],
}

describe("useLlmCatalog", () => {
  beforeEach(() => {
    apiRequestMock.mockReset()
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      return Promise.resolve({ data: null })
    })
  })

  it("serializes the explicit insecure HTTP opt-in during provider setup", async () => {
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/provider-setups") {
        return Promise.resolve({
          data: {
            provider: {
              id: "provider-relay",
              name: "Public HTTP Relay",
              kind: "openai_compatible",
              base_url: "http://8.129.13.231:8079/v1",
              scope: "user",
              enabled: true,
              allow_insecure_http: true,
              credential: { source: "stored", configured: true, available: true },
            },
            models: [],
            discovered: false,
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.setupProvider({
        templateId: "openai-compatible",
        name: "Public HTTP Relay",
        baseUrl: "http://8.129.13.231:8079/v1",
        apiKey: "relay-key",
        modelIds: ["gpt-5.6-sol"],
        allowInsecureHttp: true,
      })
    })

    expect(apiRequestMock).toHaveBeenCalledWith(
      "/llm/provider-setups",
      expect.objectContaining({
        method: "POST",
        body: expect.stringContaining('"allow_insecure_http":true'),
      }),
    )
  })

  it("returns the concrete setup error for row-level rendering", async () => {
    const failure = new Error(
      "Plain HTTP endpoints require explicit insecure HTTP approval",
    )
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/provider-setups") return Promise.reject(failure)
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let outcome: Awaited<ReturnType<typeof result.current.setupProvider>>
    await act(async () => {
      outcome = await result.current.setupProvider({
        templateId: "openai-compatible",
        baseUrl: "http://8.129.13.231:8079/v1",
      })
    })

    expect(outcome!).toEqual({ ok: false, error: failure })
    expect(result.current.error).toBe(failure)
  })
})
