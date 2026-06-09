import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LlmCatalogPanel } from "@/components/bioinfoflow/settings/llm-catalog-panel"

const useLlmCatalogMock = vi.fn()
const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()

vi.mock("@/hooks/use-llm-catalog", () => ({
  useLlmCatalog: () => useLlmCatalogMock(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      "providerCards.loading": "Loading providers...",
      "providerCards.save": "Save",
      "providerCards.saving": "Saving...",
      "providerCards.apiKeyPlaceholder": "Paste API key",
      "providerCards.savedKeyPlaceholder": "Key saved. Paste a new key to replace it.",
      "providerCards.endpointPlaceholder": "Endpoint URL",
      "providerCards.getApiKey": `Get API key${values?.provider ? ` for ${values.provider}` : ""}`,
      "providerCards.configured": "Configured",
      "providerCards.notConfigured": "Not configured",
      "providerCards.noKeyRequired": "No key required",
      "providerCards.saved": "Provider saved",
      "providerCards.saveFailed": "Provider could not be saved",
      "providerCards.refreshModels": "Refresh local models",
      "providerCards.refreshingModels": "Refreshing...",
      "providerCards.modelsDiscovered": `${values?.count ?? 0} models found`,
      "providerCards.modelsRefreshed": "Local models refreshed",
      "providerCards.modelRefreshFailed": "Local models could not be refreshed",
    }
    return labels[key] ?? key
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
  },
}))

describe("LlmCatalogPanel", () => {
  beforeEach(() => {
    useLlmCatalogMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  it("renders the provider key grid with common hosted and local providers", () => {
    useLlmCatalogMock.mockReturnValue({
      configuredProviders: [],
      isLoading: false,
      isMutating: false,
      error: null,
      createProvider: vi.fn(),
      updateProvider: vi.fn(),
      updateCredential: vi.fn(),
      discoverModels: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    for (const name of [
      "OpenAI",
      "Claude",
      "Gemini",
      "Grok",
      "DeepSeek",
      "OpenRouter",
      "Ollama",
      "GLM",
      "Minimax",
      "vLLM",
      "OpenAI Compatible",
    ]) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument()
    }

    expect(screen.queryByText("Model profiles")).not.toBeInTheDocument()
    expect(screen.queryByText("Models")).not.toBeInTheDocument()
  })

  it("keeps stored secrets write-only and updates an existing provider credential", async () => {
    const updateCredential = vi.fn().mockResolvedValue({
      configured: true,
      available: true,
    })
    useLlmCatalogMock.mockReturnValue({
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: null,
          metadata: { providerSlug: "openai" },
          enabled: true,
          credential: {
            source: "stored",
            configured: true,
            available: true,
            masked_hint: "sk-...abcd",
            fingerprint: "fp_123",
          },
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      createProvider: vi.fn(),
      updateProvider: vi.fn().mockResolvedValue({ id: "provider-openai" }),
      updateCredential,
      discoverModels: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    expect(within(card).getByText("sk-...abcd")).toBeInTheDocument()
    const input = within(card).getByLabelText("OpenAI API key")
    expect(input).toHaveValue("")

    fireEvent.change(input, { target: { value: "sk-new" } })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(updateCredential).toHaveBeenCalledWith("provider-openai", {
        source: "stored",
        envVarName: null,
        secret: "sk-new",
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
  })

  it("creates an OpenAI-compatible branded provider and does not show success when credential save fails", async () => {
    const createProvider = vi.fn().mockResolvedValue({
      id: "provider-grok",
      name: "Grok",
      kind: "openai_compatible",
      enabled: true,
    })
    const updateCredential = vi.fn().mockResolvedValue(null)
    useLlmCatalogMock.mockReturnValue({
      configuredProviders: [],
      isLoading: false,
      isMutating: false,
      error: null,
      createProvider,
      updateProvider: vi.fn(),
      updateCredential,
      discoverModels: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Grok" })
    fireEvent.change(within(card).getByLabelText("Grok API key"), {
      target: { value: "xai-key" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(createProvider).toHaveBeenCalledWith({
        name: "Grok",
        kind: "openai_compatible",
        baseUrl: "https://api.x.ai/v1",
        apiKeyRef: null,
        scope: "user",
        enabled: true,
        metadata: { providerSlug: "grok", authMode: "stored" },
      })
    })
    expect(updateCredential).toHaveBeenCalledWith("provider-grok", {
      source: "stored",
      envVarName: null,
      secret: "xai-key",
    })
    expect(toastErrorMock).toHaveBeenCalledWith("Provider could not be saved")
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it("allows endpoint-only vLLM providers without an API key", async () => {
    const createProvider = vi.fn().mockResolvedValue({
      id: "provider-vllm",
      name: "vLLM",
      kind: "vllm",
      enabled: true,
    })
    const updateCredential = vi.fn().mockResolvedValue({
      source: "none",
      configured: false,
      available: true,
    })
    useLlmCatalogMock.mockReturnValue({
      configuredProviders: [],
      isLoading: false,
      isMutating: false,
      error: null,
      createProvider,
      updateProvider: vi.fn(),
      updateCredential,
      discoverModels: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "vLLM" })
    fireEvent.change(within(card).getByLabelText("vLLM endpoint"), {
      target: { value: "http://localhost:8000/v1" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(createProvider).toHaveBeenCalledWith({
        name: "vLLM",
        kind: "vllm",
        baseUrl: "http://localhost:8000/v1",
        apiKeyRef: null,
        scope: "user",
        enabled: true,
        metadata: { providerSlug: "vllm", authMode: "none" },
      })
    })
    expect(updateCredential).toHaveBeenCalledWith("provider-vllm", {
      source: "none",
      envVarName: null,
      secret: null,
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
  })

  it("lets Ollama refresh local models without exposing advanced catalog editing", async () => {
    const discoverModels = vi.fn().mockResolvedValue([
      {
        id: "model-deepseek",
        provider_id: "provider-ollama",
        model_id: "deepseek-r1:latest",
        display_name: "DeepSeek R1",
      },
    ])
    useLlmCatalogMock.mockReturnValue({
      configuredProviders: [
        {
          id: "provider-ollama",
          name: "Ollama",
          kind: "ollama",
          base_url: "http://localhost:11434",
          metadata: { providerSlug: "ollama" },
          enabled: true,
          credential: { source: "none", configured: false, available: true },
        },
      ],
      models: [
        {
          id: "model-deepseek",
          provider_id: "provider-ollama",
          model_id: "deepseek-r1:latest",
          display_name: "DeepSeek R1",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      createProvider: vi.fn(),
      updateProvider: vi.fn(),
      updateCredential: vi.fn(),
      discoverModels,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Ollama" })
    expect(within(card).getByText("deepseek-r1:latest")).toBeInTheDocument()
    fireEvent.click(within(card).getByRole("button", { name: "Refresh local models" }))

    await waitFor(() => {
      expect(discoverModels).toHaveBeenCalledWith("provider-ollama")
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Local models refreshed")
  })
})
