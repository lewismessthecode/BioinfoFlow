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

  it("keeps the loaded catalog visible during the refresh after setup", async () => {
    let configurationCalls = 0
    let resolveBackgroundRefresh!: (value: { data: typeof emptyConfiguration }) => void
    const backgroundRefresh = new Promise<{ data: typeof emptyConfiguration }>(
      (resolve) => {
        resolveBackgroundRefresh = resolve
      },
    )
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        configurationCalls += 1
        if (configurationCalls === 1) {
          return Promise.resolve({ data: emptyConfiguration })
        }
        return backgroundRefresh
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/provider-setups") {
        return Promise.resolve({
          data: {
            provider: { id: "provider-openai" },
            models: [],
            discovered: false,
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let setupPromise!: ReturnType<typeof result.current.setupProvider>
    await act(async () => {
      setupPromise = result.current.setupProvider({ templateId: "openai" })
      await Promise.resolve()
      await Promise.resolve()
    })

    expect(result.current.isLoading).toBe(false)

    resolveBackgroundRefresh({ data: emptyConfiguration })
    await act(async () => {
      await setupPromise
    })
  })

  it("keeps mutation state active until concurrent setups finish", async () => {
    const resolvers = new Map<string, (value: { data: unknown }) => void>()
    apiRequestMock.mockImplementation((path: string, options?: { body?: string }) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/provider-setups") {
        const templateId = JSON.parse(options?.body ?? "{}").template_id as string
        return new Promise((resolve) => {
          resolvers.set(templateId, resolve)
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let openaiSetup!: ReturnType<typeof result.current.setupProvider>
    let anthropicSetup!: ReturnType<typeof result.current.setupProvider>
    act(() => {
      openaiSetup = result.current.setupProvider({ templateId: "openai" })
      anthropicSetup = result.current.setupProvider({ templateId: "anthropic" })
    })
    expect(result.current.isMutating).toBe(true)

    resolvers.get("openai")?.({
      data: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    await act(async () => {
      await openaiSetup
    })
    expect(result.current.isMutating).toBe(true)

    resolvers.get("anthropic")?.({
      data: {
        provider: { id: "provider-anthropic" },
        models: [],
        discovered: false,
      },
    })
    await act(async () => {
      await anthropicSetup
    })
    expect(result.current.isMutating).toBe(false)
  })

  it("ignores an older background refresh that finishes last", async () => {
    let configurationCalls = 0
    let resolveOlderRefresh!: (value: { data: typeof emptyConfiguration }) => void
    let resolveNewerRefresh!: (value: { data: typeof emptyConfiguration }) => void
    const olderRefresh = new Promise<{ data: typeof emptyConfiguration }>(
      (resolve) => {
        resolveOlderRefresh = resolve
      },
    )
    const newerRefresh = new Promise<{ data: typeof emptyConfiguration }>(
      (resolve) => {
        resolveNewerRefresh = resolve
      },
    )
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        configurationCalls += 1
        if (configurationCalls === 1) {
          return Promise.resolve({ data: emptyConfiguration })
        }
        return configurationCalls === 2 ? olderRefresh : newerRefresh
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/provider-setups") {
        return Promise.resolve({
          data: {
            provider: { id: "provider" },
            models: [],
            discovered: false,
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let olderSetup!: ReturnType<typeof result.current.setupProvider>
    let newerSetup!: ReturnType<typeof result.current.setupProvider>
    act(() => {
      olderSetup = result.current.setupProvider({ templateId: "openai" })
      newerSetup = result.current.setupProvider({ templateId: "anthropic" })
    })
    await waitFor(() => expect(configurationCalls).toBe(3))

    const completeConfiguration = {
      ...emptyConfiguration,
      providers: [{ id: "provider-openai" }, { id: "provider-anthropic" }],
    }
    resolveNewerRefresh({ data: completeConfiguration })
    await act(async () => {
      await newerSetup
    })

    const partialConfiguration = {
      ...emptyConfiguration,
      providers: [{ id: "provider-openai" }],
    }
    resolveOlderRefresh({ data: partialConfiguration })
    await act(async () => {
      await olderSetup
    })

    expect(result.current.configuredProviders.map((provider) => provider.id)).toEqual([
      "provider-openai",
      "provider-anthropic",
    ])
  })
})
