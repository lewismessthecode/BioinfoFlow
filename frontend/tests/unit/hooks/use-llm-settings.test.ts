import { act, renderHook, waitFor } from "@testing-library/react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// Mock apiRequest before importing the hook
const mockApiRequest = vi.fn()
vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: (...args: unknown[]) => mockApiRequest(...args),
    getApiErrorMessage: (_error: unknown, fallback: string) => fallback,
  }
})

vi.mock("sonner", () => ({
  toast: { error: vi.fn() },
}))

import { useLlmSettings } from "@/hooks/use-llm-settings"
import type { LlmRuntimeSettings, ProviderModels } from "@/hooks/use-llm-settings"
import { ApiError } from "@/lib/api"

const MOCK_SETTINGS: LlmRuntimeSettings = {
  selected_provider: "anthropic",
  selected_model: "claude-sonnet-4-20250514",
  configured_providers: ["anthropic"],
}

const MOCK_MODELS: ProviderModels[] = [
  {
    provider: "anthropic",
    provider_id: "provider-anthropic",
    label: "Anthropic",
    models: [
      {
        id: "claude-sonnet-4-20250514",
        name: "Claude Sonnet 4",
        context_window: 200000,
        model_id: "model-sonnet",
      },
      {
        id: "claude-haiku-3",
        name: "Claude Haiku 3",
        context_window: 200000,
        model_id: "model-haiku",
      },
    ],
  },
]

const MOCK_CONFIGURATION = {
  summary: {
    provider_count: 1,
    configured_provider_count: 1,
    available_provider_count: 1,
    model_count: 2,
    profile_count: 0,
  },
  providers: [
    {
      id: "provider-anthropic",
      name: "Anthropic",
      kind: "anthropic",
      enabled: true,
      credential: { configured: true, available: true },
    },
  ],
  models: [
    {
      id: "model-sonnet",
      provider_id: "provider-anthropic",
      model_id: "claude-sonnet-4-20250514",
      display_name: "Claude Sonnet 4",
      context_length: 200000,
    },
    {
      id: "model-haiku",
      provider_id: "provider-anthropic",
      model_id: "claude-haiku-3",
      display_name: "Claude Haiku 3",
      context_length: 200000,
    },
  ],
  profiles: [],
}

describe("useLlmSettings", () => {
  beforeEach(() => {
    localStorage.clear()
    mockApiRequest.mockReset()

    mockApiRequest.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: MOCK_CONFIGURATION })
      }
      return Promise.resolve({ data: null })
    })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("loads settings and models on mount", async () => {
    const { result } = renderHook(() => useLlmSettings())

    // Initially loading
    expect(result.current.isLoading).toBe(true)

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.settings).toEqual(MOCK_SETTINGS)
    expect(result.current.models).toEqual(MOCK_MODELS)
    expect(result.current.selectedModel).toEqual({
      provider: "anthropic",
      model: "claude-sonnet-4-20250514",
      model_id: "model-sonnet",
    })
    expect(result.current.hasConfiguredProvider).toBe(true)
  })

  it("flattens allModels with provider info", async () => {
    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.allModels).toEqual([
      {
        id: "claude-sonnet-4-20250514",
        name: "Claude Sonnet 4",
        context_window: 200000,
        model_id: "model-sonnet",
        provider: "anthropic",
      },
      {
        id: "claude-haiku-3",
        name: "Claude Haiku 3",
        context_window: 200000,
        model_id: "model-haiku",
        provider: "anthropic",
      },
    ])
  })

  it("syncs selected model to localStorage on fetch", async () => {
    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(localStorage.getItem("bioinfoflow:selected-model")).toBe(
      "claude-sonnet-4-20250514"
    )
  })

  it("handles API errors gracefully without crashing", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    mockApiRequest.mockRejectedValue(new Error("Network error"))

    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    // Should still be usable with null/empty defaults
    expect(result.current.settings).toBeNull()
    expect(result.current.models).toEqual([])
    expect(result.current.hasConfiguredProvider).toBe(false)
    expect(result.current.selectedModel).toBeNull()
    expect(result.current.configurationUnavailable).toBe(true)
    expect(result.current.configurationError).toBe("LLM configuration is unavailable")
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })

  it("filters out configured env providers that are not available to the runtime", async () => {
    mockApiRequest.mockImplementation((path: string) => {
      if (path === "/llm/configuration") {
        return Promise.resolve({
          data: {
            summary: {
              provider_count: 1,
              configured_provider_count: 1,
              available_provider_count: 0,
              model_count: 1,
              profile_count: 0,
            },
            providers: [
              {
                id: "provider-env",
                name: "Env Gateway",
                kind: "openai_compatible",
                credential: {
                  source: "env",
                  configured: true,
                  available: false,
                  env_var_name: "MISSING_MODEL_KEY",
                },
              },
            ],
            models: [
              {
                id: "model-env",
                provider_id: "provider-env",
                model_id: "env-model",
                display_name: "Env Model",
                context_length: 128000,
              },
            ],
            profiles: [],
          },
        })
      }
      return Promise.resolve({ data: null })
    })

    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.models).toEqual([])
    expect(result.current.hasConfiguredProvider).toBe(false)
    expect(result.current.selectedModel).toBeNull()
  })

  it("treats unauthorized initial loads as a silent unauthenticated state", async () => {
    const consoleErrorSpy = vi.spyOn(console, "error").mockImplementation(() => {})
    mockApiRequest.mockRejectedValue(
      new ApiError("Unauthorized", {
        status: 401,
      })
    )

    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    expect(result.current.settings).toBeNull()
    expect(result.current.models).toEqual([])
    expect(result.current.hasConfiguredProvider).toBe(false)
    expect(result.current.selectedModel).toBeNull()
    expect(result.current.configurationUnavailable).toBe(false)
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })

  it("testProvider uses the catalog provider test endpoint and returns failure result on API error", async () => {
    mockApiRequest.mockImplementation((path: string) => {
      if (path === "/llm/providers/provider-anthropic/test") {
        return Promise.reject(new Error("Connection refused"))
      }
      if (path === "/llm/configuration") {
        return Promise.resolve({ data: MOCK_CONFIGURATION })
      }
      return Promise.resolve({ data: null })
    })

    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let testResult: Awaited<ReturnType<typeof result.current.testProvider>>
    await act(async () => {
      testResult = await result.current.testProvider("anthropic")
    })

    expect(mockApiRequest).toHaveBeenCalledWith(
      "/llm/providers/provider-anthropic/test",
      { method: "POST" },
    )
    expect(testResult!).toEqual({
      provider: "anthropic",
      success: false,
      error: "Connection test failed",
      model: null,
    })
  })
})
