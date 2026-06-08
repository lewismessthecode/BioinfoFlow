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
import type { UserLlmSettings, ProviderModels } from "@/hooks/use-llm-settings"
import { ApiError } from "@/lib/api"

const MOCK_SETTINGS: UserLlmSettings = {
  provider_credentials: {},
  selected_provider: "anthropic",
  selected_model: "claude-sonnet-4-20250514",
  configured_providers: ["anthropic"],
}

const MOCK_MODELS: ProviderModels[] = [
  {
    provider: "anthropic",
    label: "Anthropic",
    models: [
      { id: "claude-sonnet-4-20250514", name: "Claude Sonnet 4", context_window: 200000 },
      { id: "claude-haiku-3", name: "Claude Haiku 3", context_window: 200000 },
    ],
  },
]

describe("useLlmSettings", () => {
  beforeEach(() => {
    localStorage.clear()
    mockApiRequest.mockReset()

    // Default: settings and models both resolve
    mockApiRequest.mockImplementation((path: string) => {
      if (path === "/user-settings") {
        return Promise.resolve({ data: MOCK_SETTINGS })
      }
      if (path === "/user-settings/models") {
        return Promise.resolve({ data: MOCK_MODELS })
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
        provider: "anthropic",
      },
      {
        id: "claude-haiku-3",
        name: "Claude Haiku 3",
        context_window: 200000,
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
    expect(consoleErrorSpy).not.toHaveBeenCalled()
  })

  it("testProvider returns failure result on API error", async () => {
    mockApiRequest.mockImplementation((path: string) => {
      if (path.startsWith("/user-settings/test/")) {
        return Promise.reject(new Error("Connection refused"))
      }
      // still resolve settings/models for mount
      if (path === "/user-settings") {
        return Promise.resolve({ data: MOCK_SETTINGS })
      }
      return Promise.resolve({ data: MOCK_MODELS })
    })

    const { result } = renderHook(() => useLlmSettings())

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false)
    })

    let testResult: Awaited<ReturnType<typeof result.current.testProvider>>
    await act(async () => {
      testResult = await result.current.testProvider("openai")
    })

    expect(testResult!).toEqual({
      provider: "openai",
      success: false,
      error: "Connection test failed",
      model: null,
    })
  })
})
