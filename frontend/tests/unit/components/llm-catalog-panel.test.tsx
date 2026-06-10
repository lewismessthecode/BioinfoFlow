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
      "providerCards.summary": `${values?.count ?? 0} configured`,
      "providerCards.save": "Save",
      "providerCards.saving": "Saving...",
      "providerCards.apiKeyPlaceholder": "Paste API key",
      "providerCards.savedKeyPlaceholder": "Key saved. Paste a new key to replace it.",
      "providerCards.endpointPlaceholder": "Endpoint URL",
      "providerCards.getApiKey": "Get key",
      "providerCards.noKeyRequired": "No key required",
      "providerCards.ready": "Ready",
      "providerCards.needsSetup": "Setup",
      "providerCards.fromEnv": "From .env",
      "providerCards.keySavedShort": "Key saved",
      "providerCards.saved": "Provider saved",
      "providerCards.saveFailed": "Provider could not be saved",
      "providerCards.refreshModels": "Refresh models",
      "providerCards.refreshingModels": "Refreshing...",
      "providerCards.modelsDiscovered": `${values?.count ?? 0} models found`,
      "providerCards.modelRefreshFailed": "Models could not be refreshed",
      "providerCards.modelIdPlaceholder": "Model ID",
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
  const templates = [
    providerTemplate("openai", "OpenAI", "openai", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.openai.com/v1"),
    providerTemplate("anthropic", "Anthropic", "anthropic", "anthropic_models", [
      field("api_key", "API key", true, true),
    ]),
    providerTemplate("gemini", "Gemini", "gemini", "gemini_models", [
      field("api_key", "API key", true, true),
    ]),
    providerTemplate("grok", "Grok", "grok", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.x.ai/v1"),
    providerTemplate("groq", "Groq", "groq", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.groq.com/openai/v1"),
    providerTemplate("deepseek", "DeepSeek", "deepseek", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.deepseek.com/v1"),
    providerTemplate("openrouter", "OpenRouter", "openrouter", "openai_models", [
      field("api_key", "API key", true, true),
      field("model_id", "Model ID", false, false),
    ], "https://openrouter.ai/api/v1", [
      {
        id: "openrouter/auto",
        name: "OpenRouter Auto",
        supports_tools: true,
        supports_streaming: true,
        supports_vision: false,
        supports_json_schema: true,
        supports_reasoning: false,
      },
    ]),
    providerTemplate("ollama", "Ollama", "ollama", "ollama_tags", [
      field("base_url", "Endpoint", false, true, "http://localhost:11434"),
      field("model_id", "Model ID", false, false),
    ], "http://localhost:11434"),
    providerTemplate("vllm", "vLLM", "vllm", "openai_models", [
      field("base_url", "Endpoint", false, true, "http://localhost:8000/v1"),
      field("api_key", "API key", true, false),
      field("model_id", "Model ID", false, false),
    ], "http://localhost:8000/v1"),
    providerTemplate("openai-compatible", "OpenAI Compatible", "openai_compatible", "openai_models", [
      field("base_url", "Endpoint", false, true, "https://api.example.com/v1"),
      field("api_key", "API key", true, false),
      field("model_id", "Model ID", false, false),
    ], "https://api.example.com/v1"),
  ]

  beforeEach(() => {
    useLlmCatalogMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
  })

  it("renders the provider key grid with common hosted and local providers", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    for (const name of [
      "OpenAI",
      "Anthropic",
      "Gemini",
      "Grok",
      "DeepSeek",
      "OpenRouter",
      "Ollama",
      "vLLM",
      "OpenAI Compatible",
    ]) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument()
    }

    expect(screen.queryByText("Model profiles")).not.toBeInTheDocument()
    expect(screen.queryByText("Models")).not.toBeInTheDocument()
  })

  it("keeps stored secrets write-only and updates an existing provider through setup", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      provider: { id: "provider-openai" },
      models: [],
      discovered: false,
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: null,
          metadata: { providerTemplate: "openai" },
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
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    expect(within(card).getByText("Key saved")).toBeInTheDocument()
    const input = within(card).getByLabelText("OpenAI API key")
    expect(input).toHaveValue("")

    fireEvent.change(input, { target: { value: "sk-new" } })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "openai",
        providerId: "provider-openai",
        name: "OpenAI",
        apiKey: "sk-new",
        baseUrl: "https://api.openai.com/v1",
        modelIds: [],
        discover: true,
        scope: "user",
        enabled: true,
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
  })

  it("sets up a branded provider and does not show success when setup fails", async () => {
    const setupProvider = vi.fn().mockResolvedValue(null)
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Grok" })
    fireEvent.change(within(card).getByLabelText("Grok API key"), {
      target: { value: "xai-key" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "grok",
        name: "Grok",
        baseUrl: "https://api.x.ai/v1",
        apiKey: "xai-key",
        modelIds: [],
        discover: true,
        scope: "user",
        enabled: true,
      })
    })
    expect(toastErrorMock).toHaveBeenCalledWith("Provider could not be saved")
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it("sets up endpoint-only vLLM with a manual model id in one save", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      provider: { id: "provider-vllm" },
      models: [{ id: "model-vllm", model_id: "deepseek_v4" }],
      discovered: false,
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "vLLM" })
    fireEvent.change(within(card).getByLabelText("vLLM endpoint"), {
      target: { value: "http://localhost:8000/v1" },
    })
    fireEvent.change(within(card).getByLabelText("vLLM model id"), {
      target: { value: "deepseek_v4" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "vllm",
        name: "vLLM",
        baseUrl: "http://localhost:8000/v1",
        apiKey: "",
        modelIds: ["deepseek_v4"],
        discover: true,
        scope: "user",
        enabled: true,
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
  })

  it("lets discoverable providers refresh models through provider setup", async () => {
    const setupProvider = vi.fn()
    const discoverModels = vi.fn().mockResolvedValue([
      { id: "model-deepseek", model_id: "deepseek-r1:latest" },
    ])
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-ollama",
          name: "Ollama",
          kind: "ollama",
          base_url: "http://localhost:11434",
          metadata: { providerTemplate: "ollama" },
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
      discoverModels,
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Ollama" })
    expect(card).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Refresh models" }))

    await waitFor(() => {
      expect(discoverModels).toHaveBeenCalledWith("provider-ollama")
    })
    expect(setupProvider).not.toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalledWith("1 models found")
  })
})

function field(
  name: string,
  label: string,
  secret: boolean,
  required: boolean,
  defaultValue?: string,
) {
  return {
    name,
    label,
    secret,
    required,
    placeholder: label,
    default: defaultValue,
  }
}

function providerTemplate(
  id: string,
  name: string,
  kind: string,
  discovery: string,
  fields: ReturnType<typeof field>[],
  defaultBaseUrl?: string,
  models: Array<Record<string, unknown>> = [],
) {
  return {
    id,
    name,
    kind,
    docs_url: `https://docs.example.com/${id}`,
    discovery,
    default_base_url: defaultBaseUrl,
    fields,
    models,
  }
}
