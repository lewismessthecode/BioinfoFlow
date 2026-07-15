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
              base_url: "http://public-relay.example:8079/v1",
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
        baseUrl: "http://public-relay.example:8079/v1",
        apiKey: "relay-key",
        modelIds: ["gpt-5.6-sol"],
        wireProtocol: "responses",
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
    const setupCall = apiRequestMock.mock.calls.find(
      ([path]) => path === "/llm/provider-setups",
    )
    expect(JSON.parse(setupCall?.[1]?.body ?? "{}")).toMatchObject({
      wire_protocol: "responses",
    })
  })

  it("preserves provider and template wire protocol capabilities from the API", async () => {
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({
          data: {
            ...emptyConfiguration,
            providers: [
              {
                id: "provider-relay",
                wire_protocol: "responses",
                credential: {
                  source: "stored",
                  configured: true,
                  available: true,
                },
              },
            ],
          },
        })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({
          data: [
            {
              id: "openai-compatible",
              supported_wire_protocols: ["chat_completions", "responses"],
              default_wire_protocol: "chat_completions",
            },
          ],
        })
      }
      return Promise.resolve({ data: null })
    })

    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.configuredProviders[0]?.wire_protocol).toBe("responses")
    expect(result.current.providerTemplates[0]?.supported_wire_protocols).toEqual([
      "chat_completions",
      "responses",
    ])
    expect(result.current.providerTemplates[0]?.default_wire_protocol).toBe(
      "chat_completions",
    )
  })

  it("serializes wire protocol when creating and updating providers", async () => {
    apiRequestMock.mockImplementation((path: string, options?: { body?: string }) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/providers") {
        return Promise.resolve({
          data: {
            id: "provider-relay",
            wire_protocol: JSON.parse(options?.body ?? "{}").wire_protocol,
          },
        })
      }
      if (path === "/llm/providers/provider-relay") {
        return Promise.resolve({
          data: {
            id: "provider-relay",
            wire_protocol: JSON.parse(options?.body ?? "{}").wire_protocol,
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    await act(async () => {
      await result.current.createProvider({
        name: "Relay",
        kind: "openai_compatible",
        wireProtocol: "responses",
      })
      await result.current.updateProvider("provider-relay", {
        wireProtocol: "chat_completions",
      })
    })

    const createCall = apiRequestMock.mock.calls.find(
      ([path]) => path === "/llm/providers",
    )
    const updateCall = apiRequestMock.mock.calls.find(
      ([path]) => path === "/llm/providers/provider-relay",
    )
    expect(JSON.parse(createCall?.[1]?.body ?? "{}").wire_protocol).toBe("responses")
    expect(JSON.parse(updateCall?.[1]?.body ?? "{}").wire_protocol).toBe(
      "chat_completions",
    )
  })

  it("omits an unspecified wire protocol from provider setup requests", async () => {
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
            provider: { id: "provider-relay" },
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
        providerId: "provider-relay",
      })
    })

    const setupCall = apiRequestMock.mock.calls.find(
      ([path]) => path === "/llm/provider-setups",
    )
    expect(JSON.parse(setupCall?.[1]?.body ?? "{}")).not.toHaveProperty(
      "wire_protocol",
    )
  })

  it("tests an optional selected model and returns the full safe probe result", async () => {
    let configurationCalls = 0
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        configurationCalls += 1
        return Promise.resolve({ data: emptyConfiguration })
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/providers/provider-relay/test") {
        return Promise.resolve({
          data: {
            provider_id: "provider-relay",
            success: false,
            model: "gpt-5.4-mini",
            wire_protocol: "responses",
            error_code: "service_unavailable",
            error: "The model provider is temporarily unavailable.",
            latency_ms: 125,
            retryable: true,
            http_status: 503,
            provider_code: "server_error",
          },
        })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let probeResult: Awaited<ReturnType<typeof result.current.testProvider>>
    await act(async () => {
      probeResult = await result.current.testProvider(
        "provider-relay",
        "model-record-id",
      )
    })

    expect(probeResult!).toEqual({
      provider_id: "provider-relay",
      success: false,
      model: "gpt-5.4-mini",
      wire_protocol: "responses",
      error_code: "service_unavailable",
      error: "The model provider is temporarily unavailable.",
      latency_ms: 125,
      retryable: true,
      http_status: 503,
      provider_code: "server_error",
    })
    expect(apiRequestMock).toHaveBeenCalledWith(
      "/llm/providers/provider-relay/test",
      {
        method: "POST",
        body: JSON.stringify({ model_id: "model-record-id" }),
      },
    )
    expect(configurationCalls).toBe(2)
  })

  it("keeps discovered models when the follow-up catalog refresh fails", async () => {
    let configurationCalls = 0
    const discoveredModel = {
      id: "model-relay",
      provider_id: "provider-relay",
      model_id: "gpt-5.4-mini",
      display_name: "GPT-5.4 Mini",
      context_length: null,
      max_output_tokens: null,
      supports_tools: true,
      supports_streaming: true,
      supports_vision: false,
      supports_json_schema: true,
      supports_reasoning: true,
      default_temperature: null,
      default_top_p: null,
      cost_metadata: null,
      metadata: null,
      created_at: "2026-07-14T00:00:00Z",
      updated_at: "2026-07-14T00:00:00Z",
    }
    apiRequestMock.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        configurationCalls += 1
        return configurationCalls === 1
          ? Promise.resolve({ data: emptyConfiguration })
          : Promise.reject(new Error("catalog refresh failed"))
      }
      if (path === "/llm/provider-templates") {
        return Promise.resolve({ data: [] })
      }
      if (path === "/llm/providers/provider-relay/discover-models") {
        return Promise.resolve({ data: [discoveredModel] })
      }
      return Promise.resolve({ data: null })
    })
    const { result } = renderHook(() => useLlmCatalog())
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    let discovered: Awaited<ReturnType<typeof result.current.discoverModels>>
    await act(async () => {
      discovered = await result.current.discoverModels("provider-relay")
    })

    expect(discovered!).toEqual([discoveredModel])
    expect(result.current.models).toEqual([discoveredModel])
    expect(result.current.error?.message).toBe("catalog refresh failed")
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
        baseUrl: "http://public-relay.example:8079/v1",
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
