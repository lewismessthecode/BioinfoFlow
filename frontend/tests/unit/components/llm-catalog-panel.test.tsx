import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LlmCatalogPanel } from "@/components/bioinfoflow/settings/llm-catalog-panel"

const useLlmCatalogMock = vi.fn()
const useLlmSettingsMock = vi.fn()
const useProviderConnectionMock = vi.fn()
const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
const toastWarningMock = vi.fn()
const celebrateMilestoneMock = vi.fn()

vi.mock("@/hooks/use-llm-catalog", () => ({
  useLlmCatalog: () => useLlmCatalogMock(),
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: () => useLlmSettingsMock(),
}))

vi.mock("@/hooks/use-provider-connection", () => ({
  useProviderConnection: (...args: unknown[]) => useProviderConnectionMock(...args),
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
      "providerCards.savedDiscoveryFailed":
        "Provider saved, but model discovery failed",
      "providerCards.savedNoModels": "Provider saved, but no models were found",
      "providerCards.modelRefreshFailed": "Models could not be refreshed",
      "providerCards.remove": "Remove",
      "providerCards.confirmRemove": "Confirm remove",
      "providerCards.removing": "Removing...",
      "providerCards.removed": "Provider removed",
      "providerCards.removeFailed": "Provider could not be removed",
      "providerCards.modelIdPlaceholder": "Model ID",
      "providerCards.allowInsecureHttp": "Allow insecure HTTP",
      "providerCards.insecureHttpDescription":
        "API keys and prompts are sent without TLS.",
      "providerCards.insecureHttpEnabled": "Insecure transport allowed",
      "providerCards.insecureHttpOn": "On",
      "providerCards.insecureHttpOff": "Off",
      "providerCards.loadFailed": "Providers could not be loaded",
      "providerCards.retry": "Retry",
      "providerCards.endpointLabel": "Endpoint",
      "providerCards.apiKeyLabel": "API key",
      "providerCards.modelIdLabel": "Model ID",
      "providerCards.protocolLabel": "Protocol",
      "providerCards.protocolChat": "Chat Completions",
      "providerCards.protocolResponses": "Responses",
      "providerCards.test": "Test",
      "providerCards.testing": "Testing...",
      "providerCards.testModelLabel": "Test model",
      "providerCards.noTestModels": "No model available",
      "providerCards.testSucceeded": "Connection verified",
      "providerCards.testFailed": "Connection failed",
      "providerCards.retryable": "Retryable",
      "providerCards.settingsChanged": "Settings changed. Save and test again.",
      "providerCards.testRequestFailed": "Provider test could not be completed.",
      "providerCards.protocolAriaLabel": `${values?.provider ?? ""} protocol`,
      "providerCards.testModelAriaLabel": `${values?.provider ?? ""} test model`,
    }
    return labels[key] ?? key
  },
}))

vi.mock("sonner", () => ({
  toast: {
    error: (...args: unknown[]) => toastErrorMock(...args),
    success: (...args: unknown[]) => toastSuccessMock(...args),
    warning: (...args: unknown[]) => toastWarningMock(...args),
  },
}))

vi.mock("@/lib/celebrations", () => ({
  celebrateMilestone: (...args: unknown[]) => celebrateMilestoneMock(...args),
}))

describe("LlmCatalogPanel", () => {
  const templates = [
    providerTemplate("openai", "OpenAI", "openai", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.openai.com/v1"),
    providerTemplate("anthropic", "Anthropic", "anthropic", "anthropic_models", [
      field("api_key", "API key", true, true),
    ], "https://api.anthropic.com"),
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
    providerTemplate("kimi", "Kimi", "kimi", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.moonshot.ai/v1", [], "https://platform.kimi.ai/console/api-keys"),
    providerTemplate("kimi-cn", "Kimi China", "kimi_cn", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.moonshot.cn/v1", [], "https://platform.kimi.com/console/api-keys"),
    providerTemplate("qwen", "Qwen", "qwen", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://dashscope.aliyuncs.com/compatible-mode/v1"),
    providerTemplate("mistral", "Mistral", "mistral", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.mistral.ai/v1"),
    providerTemplate("cohere", "Cohere", "cohere", "cohere_models", [
      field("api_key", "API key", true, true),
    ], "https://api.cohere.ai/compatibility/v1"),
    providerTemplate("together", "Together AI", "together", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.together.ai/v1"),
    providerTemplate("fireworks", "Fireworks AI", "fireworks", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.fireworks.ai/inference/v1"),
    providerTemplate("perplexity", "Perplexity", "perplexity", "static", [
      field("api_key", "API key", true, true),
    ], "https://api.perplexity.ai"),
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
    useLlmSettingsMock.mockReset()
    useProviderConnectionMock.mockReset()
    toastErrorMock.mockReset()
    toastSuccessMock.mockReset()
    toastWarningMock.mockReset()
    celebrateMilestoneMock.mockReset()
    useLlmSettingsMock.mockReturnValue({
      setSelectedModel: vi.fn(),
      refresh: vi.fn(),
    })
    useProviderConnectionMock.mockImplementation((operations) => ({
      isConnecting: false,
      connect: async (input: Record<string, unknown>) => {
        const setup = await operations.setupProvider({ ...input, discover: false })
        if (!setup.ok) return { ok: false, stage: "setup", error: setup.error }
        const providerId = setup.result.provider.id
        if (setup.result.models.length === 0) {
          const discovered = await operations.discoverModels(providerId)
          if (discovered === null) {
            return {
              ok: false,
              stage: "discovery",
              error: new Error("discovery failed"),
              providerId,
            }
          }
          if (Array.isArray(discovered) && discovered.length === 0) {
            return {
              ok: false,
              stage: "model",
              error: new Error("no models"),
              providerId,
            }
          }
        }
        return {
          ok: true,
          providerId,
          modelId: setup.result.models[0]?.id ?? "model-test",
          modelName: setup.result.models[0]?.model_id ?? "model-test",
        }
      },
    }))
  })

  it("uses the shared provider connection operation for hosted quick setup", async () => {
    const connect = vi.fn().mockResolvedValue({
      ok: true,
      providerId: "provider-openai",
      modelId: "model-gpt",
      modelName: "gpt-5.4-mini",
    })
    useProviderConnectionMock.mockReturnValue({ connect, isConnecting: false })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)
    expect(useLlmSettingsMock).not.toHaveBeenCalled()
    expect(useProviderConnectionMock).toHaveBeenCalledWith(
      expect.objectContaining({
        activation: { mode: "preserve" },
      }),
    )
    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-new" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(connect).toHaveBeenCalledWith(
        expect.objectContaining({ templateId: "openai", apiKey: "sk-new" }),
      ),
    )
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
      "Kimi",
      "Kimi China",
      "Qwen",
      "Mistral",
      "Cohere",
      "Together AI",
      "Fireworks AI",
      "Perplexity",
      "Ollama",
      "vLLM",
      "OpenAI Compatible",
    ]) {
      expect(screen.getByRole("group", { name })).toBeInTheDocument()
    }

    expect(screen.queryByText("Model profiles")).not.toBeInTheDocument()
    expect(screen.queryByText("Models")).not.toBeInTheDocument()
    expect(
      within(screen.getByRole("group", { name: "Kimi" })).getByRole("link", {
        name: "Get key",
      }),
    ).toHaveAttribute("href", "https://platform.kimi.ai/console/api-keys")
    expect(
      within(screen.getByRole("group", { name: "Kimi China" })).getByRole("link", {
        name: "Get key",
      }),
    ).toHaveAttribute("href", "https://platform.kimi.com/console/api-keys")
  })

  it("shows a compact protocol selector only for multi-protocol providers and restores saved Responses", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "responses",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const openaiCard = screen.getByRole("group", { name: "OpenAI" })
    expect(within(openaiCard).getByLabelText("OpenAI protocol")).toHaveValue(
      "responses",
    )
    const anthropicCard = screen.getByRole("group", { name: "Anthropic" })
    expect(
      within(anthropicCard).queryByLabelText("Anthropic protocol"),
    ).not.toBeInTheDocument()
  })

  it("keeps hosted providers key-first without endpoint or model fields", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Anthropic" })
    expect(within(card).getByLabelText("Anthropic API key")).toHaveAttribute(
      "placeholder",
      "Paste API key",
    )
    expect(within(card).queryByLabelText("Anthropic endpoint")).not.toBeInTheDocument()
    expect(within(card).queryByLabelText("Anthropic model id")).not.toBeInTheDocument()
    expect(
      within(card).queryByLabelText("Anthropic protocol"),
    ).not.toBeInTheDocument()
  })

  it("saves the selected protocol without coupling Save to Test", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai", wire_protocol: "responses" },
        models: [],
        discovered: false,
      },
    })
    const testProvider = vi.fn()
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
      testProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-new" },
    })
    fireEvent.change(within(card).getByLabelText("OpenAI protocol"), {
      target: { value: "responses" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(setupProvider).toHaveBeenCalledWith(
        expect.objectContaining({ wireProtocol: "responses" }),
      ),
    )
    expect(testProvider).not.toHaveBeenCalled()
  })

  it("tests a selected model separately and renders safe success status", async () => {
    const testProvider = vi.fn().mockResolvedValue({
      provider_id: "provider-relay",
      success: true,
      model: "gpt-5.4",
      wire_protocol: "responses",
      latency_ms: 42,
      retryable: false,
    })
    const setupProvider = vi.fn()
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-relay",
          name: "OpenAI Compatible",
          kind: "openai_compatible",
          wire_protocol: "responses",
          metadata: { providerTemplate: "openai-compatible" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-relay",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
        {
          id: "model-two",
          provider_id: "provider-relay",
          model_id: "gpt-5.4",
          display_name: "GPT 5.4",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
      testProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible test model"), {
      target: { value: "model-two" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Test" }))

    await waitFor(() => {
      expect(testProvider).toHaveBeenCalledWith("provider-relay", "model-two")
    })
    expect(setupProvider).not.toHaveBeenCalled()
    const status = await within(card).findByRole("status")
    expect(within(status).getByText("Connection verified")).toBeInTheDocument()
    expect(within(status).getByText("Responses")).toBeInTheDocument()
    expect(within(status).getByText("gpt-5.4")).toBeInTheDocument()
    expect(within(status).getByText("42 ms")).toBeInTheDocument()
  })

  it("clears a local probe result when the selected test model changes", async () => {
    const testProvider = vi.fn().mockResolvedValue({
      provider_id: "provider-relay",
      success: true,
      model: "gpt-5.4-mini",
      wire_protocol: "responses",
      latency_ms: 42,
      retryable: false,
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-relay",
          name: "OpenAI Compatible",
          kind: "openai_compatible",
          wire_protocol: "responses",
          metadata: { providerTemplate: "openai-compatible" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-relay",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
        {
          id: "model-two",
          provider_id: "provider-relay",
          model_id: "gpt-5.4",
          display_name: "GPT 5.4",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.click(within(card).getByRole("button", { name: "Test" }))
    expect(await within(card).findByRole("status")).toHaveTextContent(
      "gpt-5.4-mini",
    )

    fireEvent.change(within(card).getByLabelText("OpenAI Compatible test model"), {
      target: { value: "model-two" },
    })

    expect(within(card).queryByRole("status")).not.toBeInTheDocument()
  })

  it("hides persisted probe status for a different selected model", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-relay",
          name: "OpenAI Compatible",
          kind: "openai_compatible",
          wire_protocol: "responses",
          metadata: { providerTemplate: "openai-compatible" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
          test_status: {
            success: true,
            model: "gpt-5.4",
            wire_protocol: "responses",
            latency_ms: 42,
            retryable: false,
          },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-relay",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
        {
          id: "model-two",
          provider_id: "provider-relay",
          model_id: "gpt-5.4",
          display_name: "GPT 5.4",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    expect(within(card).getByLabelText("OpenAI Compatible test model")).toHaveValue(
      "model-one",
    )
    expect(within(card).queryByRole("status")).not.toBeInTheDocument()
  })

  it("renders safe probe failure details and disables Test without models", async () => {
    const testProvider = vi.fn().mockResolvedValue({
      provider_id: "provider-openai",
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
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "responses",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider,
    })

    const { rerender } = render(<LlmCatalogPanel />)
    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.click(within(card).getByRole("button", { name: "Test" }))

    expect(await within(card).findByText("Connection failed")).toBeInTheDocument()
    expect(
      within(card).getByText("The model provider is temporarily unavailable."),
    ).toBeInTheDocument()
    expect(within(card).getByText("Retryable")).toBeInTheDocument()

    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "responses",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider,
    })
    rerender(<LlmCatalogPanel />)
    expect(
      within(screen.getByRole("group", { name: "OpenAI" })).getByRole("button", {
        name: "Test",
      }),
    ).toBeDisabled()
    expect(screen.getByText("No model available")).toBeInTheDocument()
  })

  it("renders a row error when the provider test request fails", async () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "responses",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn().mockResolvedValue(null),
    })

    render(<LlmCatalogPanel />)
    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.click(within(card).getByRole("button", { name: "Test" }))

    expect(
      await within(card).findByText("Provider test could not be completed."),
    ).toBeInTheDocument()
    expect(toastErrorMock).toHaveBeenCalledWith(
      "Provider test could not be completed.",
    )
  })

  it("hides a saved probe status after unsaved protocol edits", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "chat_completions",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
          test_status: {
            success: true,
            model: "gpt-5.4-mini",
            wire_protocol: "chat_completions",
            latency_ms: 24,
            retryable: false,
          },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)
    const card = screen.getByRole("group", { name: "OpenAI" })
    expect(within(card).getByText("Connection verified")).toBeInTheDocument()

    fireEvent.change(within(card).getByLabelText("OpenAI protocol"), {
      target: { value: "responses" },
    })

    expect(within(card).queryByText("Connection verified")).not.toBeInTheDocument()
    expect(
      within(card).getByText("Settings changed. Save and test again."),
    ).toBeInTheDocument()
    expect(within(card).getByRole("button", { name: "Test" })).toBeDisabled()
  })

  it("marks a saved probe status stale after credential edits", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "chat_completions",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
          test_status: {
            success: true,
            model: "gpt-5.4-mini",
            wire_protocol: "chat_completions",
            latency_ms: 24,
            retryable: false,
          },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)
    const card = screen.getByRole("group", { name: "OpenAI" })
    expect(within(card).getByText("Connection verified")).toBeInTheDocument()

    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "replacement-key" },
    })

    expect(within(card).queryByText("Connection verified")).not.toBeInTheDocument()
    expect(
      within(card).getByText("Settings changed. Save and test again."),
    ).toBeInTheDocument()
    expect(within(card).getByRole("button", { name: "Test" })).toBeDisabled()
  })

  it("discards a late probe result after settings change and save", async () => {
    let resolveProbe!: (value: {
      provider_id: string
      success: boolean
      model: string
      wire_protocol: "responses"
      latency_ms: number
      retryable: boolean
    }) => void
    const testProvider = vi.fn(
      () =>
        new Promise<Parameters<typeof resolveProbe>[0]>((resolve) => {
          resolveProbe = resolve
        }),
    )
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai", wire_protocol: "responses" },
        models: [],
        discovered: false,
      },
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          wire_protocol: "responses",
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-one",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
      testProvider,
    })

    render(<LlmCatalogPanel />)
    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.click(within(card).getByRole("button", { name: "Test" }))
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "replacement-key" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))
    await waitFor(() => expect(setupProvider).toHaveBeenCalled())

    resolveProbe({
      provider_id: "provider-openai",
      success: true,
      model: "gpt-5.4-mini",
      wire_protocol: "responses",
      latency_ms: 42,
      retryable: false,
    })

    await waitFor(() =>
      expect(within(card).getByRole("button", { name: "Test" })).toBeEnabled(),
    )
    expect(testProvider).toHaveBeenCalledTimes(1)
    expect(within(card).queryByText("Connection verified")).not.toBeInTheDocument()
  })

  it("keeps stored secrets write-only and resets hidden hosted endpoints through setup", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: "https://old-gateway.example/v1",
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
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
        wireProtocol: "chat_completions",
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
  })

  it("discovers models after saving a discoverable provider without model ids", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    const discoverModels = vi.fn().mockResolvedValue([
      { id: "model-openai", model_id: "gpt-5.4-mini" },
    ])
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels,
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-new" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith(
        expect.objectContaining({ discover: false, modelIds: [] }),
      )
      expect(discoverModels).toHaveBeenCalledWith("provider-openai")
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
  })

  it("keeps the provider saved when automatic model discovery fails", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    const discoverModels = vi.fn().mockResolvedValue(null)
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels,
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    const apiKeyInput = within(card).getByLabelText("OpenAI API key")
    fireEvent.change(apiKeyInput, { target: { value: "sk-new" } })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(toastWarningMock).toHaveBeenCalledWith(
        "Provider saved, but model discovery failed",
      ),
    )
    expect(
      within(card).getByText("Provider saved, but model discovery failed"),
    ).toBeInTheDocument()
    expect(apiKeyInput).toHaveValue("")
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it("matches a legacy Kimi cn endpoint to Kimi China instead of global Kimi", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-kimi-legacy",
          name: "Kimi",
          kind: "kimi",
          base_url: "https://api.moonshot.cn/v1",
          metadata: { providerTemplate: "kimi" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      setProviderEnabled: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    expect(
      within(screen.getByRole("group", { name: "Kimi" })).getByText("Setup"),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole("group", { name: "Kimi China" })).getByText("Ready"),
    ).toBeInTheDocument()
  })

  it("matches a legacy Kimi cn endpoint without metadata to Kimi China", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-kimi-legacy",
          name: "Kimi",
          kind: "kimi",
          base_url: "https://api.moonshot.cn/v1",
          metadata: null,
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      setProviderEnabled: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    expect(
      within(screen.getByRole("group", { name: "Kimi" })).getByText("Setup"),
    ).toBeInTheDocument()
    expect(
      within(screen.getByRole("group", { name: "Kimi China" })).getByText("Ready"),
    ).toBeInTheDocument()
  })

  it("does not show saved-key artifacts for a removed provider row", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: "https://api.openai.com/v1",
          metadata: { providerTemplate: "openai" },
          enabled: false,
          credential: {
            source: "stored",
            configured: true,
            available: true,
            masked_hint: "sk-...old",
          },
        },
      ],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
      setProviderEnabled: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    expect(within(card).getByText("Setup")).toBeInTheDocument()
    expect(within(card).queryByText("Key saved")).not.toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "Remove" })).not.toBeInTheDocument()
    expect(within(card).queryByRole("button", { name: "Test" })).not.toBeInTheDocument()
  })

  it("lets a saved provider configuration be removed from the catalog", async () => {
    const setProviderEnabled = vi.fn().mockResolvedValue({
      id: "provider-openai",
      enabled: false,
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [
        {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: "https://api.openai.com/v1",
          metadata: { providerTemplate: "openai" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
      ],
      models: [
        {
          id: "model-openai",
          provider_id: "provider-openai",
          model_id: "gpt-5.4-mini",
          display_name: "GPT 5.4 Mini",
        },
      ],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
      testProvider: vi.fn(),
      setProviderEnabled,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-replacement-before-remove" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Remove" }))
    expect(setProviderEnabled).not.toHaveBeenCalled()
    fireEvent.click(within(card).getByRole("button", { name: "Confirm remove" }))

    await waitFor(() => {
      expect(setProviderEnabled).toHaveBeenCalledWith(
        expect.objectContaining({ id: "provider-openai" }),
        false,
      )
    })
    expect(within(card).getByLabelText("OpenAI API key")).toHaveValue("")
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider removed")
  })

  it("warns when automatic model discovery finds no models", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    const discoverModels = vi.fn().mockResolvedValue([])
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels,
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-new" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() =>
      expect(toastWarningMock).toHaveBeenCalledWith(
        "Provider saved, but no models were found",
      ),
    )
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(toastSuccessMock).not.toHaveBeenCalled()
  })

  it("celebrates the first provider key when setup creates the first usable keyed provider", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: {
          id: "provider-openai",
          name: "OpenAI",
          kind: "openai",
          base_url: "https://api.openai.com/v1",
          metadata: { providerTemplate: "openai" },
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
        models: [],
        discovered: false,
      },
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

    const card = screen.getByRole("group", { name: "OpenAI" })
    fireEvent.change(within(card).getByLabelText("OpenAI API key"), {
      target: { value: "sk-first" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "openai",
        providerId: undefined,
        name: "OpenAI",
        apiKey: "sk-first",
        baseUrl: "https://api.openai.com/v1",
        modelIds: [],
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
        wireProtocol: "chat_completions",
      })
    })
    expect(celebrateMilestoneMock).toHaveBeenCalledWith("first-provider-key")
  })

  it("sets up a branded provider and does not show success when setup fails", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: false,
      error: new Error("Provider could not be saved"),
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

    const card = screen.getByRole("group", { name: "Grok" })
    fireEvent.change(within(card).getByLabelText("Grok API key"), {
      target: { value: "xai-key" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "grok",
        providerId: undefined,
        name: "Grok",
        baseUrl: "https://api.x.ai/v1",
        apiKey: "xai-key",
        modelIds: [],
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
        wireProtocol: "chat_completions",
      })
    })
    expect(toastErrorMock).toHaveBeenCalledWith("Provider could not be saved")
    expect(toastSuccessMock).not.toHaveBeenCalled()
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
  })

  it("sets up endpoint-only vLLM with a manual model id in one save", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-vllm" },
        models: [{ id: "model-vllm", model_id: "deepseek_v4" }],
        discovered: false,
      },
    })
    const discoverModels = vi.fn()
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels,
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
        providerId: undefined,
        name: "vLLM",
        baseUrl: "http://localhost:8000/v1",
        apiKey: "",
        modelIds: ["deepseek_v4"],
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
        wireProtocol: "chat_completions",
      })
    })
    expect(discoverModels).not.toHaveBeenCalled()
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
  })

  it("does not discover models after saving a static provider", async () => {
    const staticTemplate = providerTemplate(
      "static-provider",
      "Static Provider",
      "static_provider",
      "static",
      [field("api_key", "API key", true, true)],
    )
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-static" },
        models: [],
        discovered: false,
      },
    })
    const discoverModels = vi.fn()
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: [staticTemplate],
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      discoverModels,
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Static Provider" })
    fireEvent.change(within(card).getByLabelText("Static Provider API key"), {
      target: { value: "static-key" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => expect(setupProvider).toHaveBeenCalled())
    expect(discoverModels).not.toHaveBeenCalled()
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

  it("requires an explicit switch for a public HTTP provider endpoint", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: {
          id: "provider-relay",
          name: "OpenAI Compatible",
          kind: "openai_compatible",
          base_url: "http://public-relay.example:8079/v1",
          allow_insecure_http: true,
          enabled: true,
          credential: { source: "stored", configured: true, available: true },
        },
        models: [{ id: "relay-model", model_id: "gpt-5.6-sol" }],
        discovered: false,
      },
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible endpoint"), {
      target: { value: "http://public-relay.example:8079/v1" },
    })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible API key"), {
      target: { value: "relay-key" },
    })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible model id"), {
      target: { value: "gpt-5.6-sol" },
    })

    const insecureSwitch = within(card).getByRole("switch", {
      name: "Allow insecure HTTP",
    })
    const saveButton = within(card).getByRole("button", { name: "Save" })
    expect(insecureSwitch).not.toBeChecked()
    expect(within(card).getByText("Off")).toBeInTheDocument()
    expect(saveButton).toBeDisabled()
    fireEvent.click(saveButton)
    expect(setupProvider).not.toHaveBeenCalled()

    fireEvent.click(insecureSwitch)
    expect(within(card).getByText("On")).toBeInTheDocument()
    expect(saveButton).toBeEnabled()
    fireEvent.click(saveButton)

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "openai-compatible",
        providerId: undefined,
        name: "OpenAI Compatible",
        baseUrl: "http://public-relay.example:8079/v1",
        apiKey: "relay-key",
        modelIds: ["gpt-5.6-sol"],
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: true,
        wireProtocol: "chat_completions",
      })
    })
  })

  it("shows the insecure HTTP switch for a public IPv6 endpoint", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible endpoint"), {
      target: { value: "http://[2001:4860:4860::8888]:8079/v1" },
    })

    expect(
      within(card).getByRole("switch", { name: "Allow insecure HTTP" }),
    ).toBeInTheDocument()
  })

  it("keeps the insecure HTTP switch hidden for a private IPv6 endpoint", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible endpoint"), {
      target: { value: "http://[fd00::1]:8079/v1" },
    })

    expect(
      within(card).queryByRole("switch", { name: "Allow insecure HTTP" }),
    ).not.toBeInTheDocument()
  })

  it("saves a hosted Kimi provider with only an API key", async () => {
    const discoverModels = vi.fn().mockResolvedValue([
      { id: "model-kimi", model_id: "kimi-k2" },
    ])
    const setupProvider = vi.fn().mockResolvedValue({
      ok: true,
      result: {
        provider: { id: "provider-kimi", wire_protocol: "chat_completions" },
        models: [],
        discovered: false,
      },
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels,
      setupProvider,
      testProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "Kimi" })
    fireEvent.change(within(card).getByLabelText("Kimi API key"), {
      target: { value: "sk-moonshot" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "kimi",
        providerId: undefined,
        name: "Kimi",
        apiKey: "sk-moonshot",
        baseUrl: "https://api.moonshot.ai/v1",
        modelIds: [],
        discover: false,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
        wireProtocol: "chat_completions",
      })
    })
    expect(discoverModels).toHaveBeenCalledWith("provider-kimi")
    expect(toastSuccessMock).toHaveBeenCalledWith("1 models found")
  })

  it("keeps other provider rows interactive while one provider is saving", async () => {
    let resolveSetup!: (value: unknown) => void
    const catalog = {
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    }
    catalog.setupProvider.mockImplementation(
      () => new Promise((resolve) => {
        catalog.isMutating = true
        resolveSetup = resolve
      }),
    )
    useLlmCatalogMock.mockImplementation(() => catalog)

    render(<LlmCatalogPanel />)

    const openaiCard = screen.getByRole("group", { name: "OpenAI" })
    const anthropicCard = screen.getByRole("group", { name: "Anthropic" })
    fireEvent.change(within(openaiCard).getByLabelText("OpenAI API key"), {
      target: { value: "openai-key" },
    })
    fireEvent.change(within(anthropicCard).getByLabelText("Anthropic API key"), {
      target: { value: "anthropic-key" },
    })
    fireEvent.click(within(openaiCard).getByRole("button", { name: "Save" }))

    expect(
      within(anthropicCard).getByRole("button", { name: "Save" }),
    ).toBeEnabled()

    catalog.isMutating = false
    resolveSetup({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    await waitFor(() => expect(toastSuccessMock).toHaveBeenCalled())
  })

  it("tracks concurrent provider saves independently", async () => {
    const resolvers = new Map<string, (value: unknown) => void>()
    const setupProvider = vi.fn().mockImplementation(
      (input: { templateId: string }) => new Promise((resolve) => {
        resolvers.set(input.templateId, resolve)
      }),
    )
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: true,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const openaiCard = screen.getByRole("group", { name: "OpenAI" })
    const anthropicCard = screen.getByRole("group", { name: "Anthropic" })
    fireEvent.change(within(openaiCard).getByLabelText("OpenAI API key"), {
      target: { value: "openai-key" },
    })
    fireEvent.change(within(anthropicCard).getByLabelText("Anthropic API key"), {
      target: { value: "anthropic-key" },
    })
    fireEvent.click(within(openaiCard).getByRole("button", { name: "Save" }))
    fireEvent.click(within(anthropicCard).getByRole("button", { name: "Save" }))

    expect(
      within(openaiCard).getByRole("button", { name: "Saving..." }),
    ).toBeDisabled()
    expect(
      within(anthropicCard).getByRole("button", { name: "Saving..." }),
    ).toBeDisabled()

    resolvers.get("openai")?.({
      ok: true,
      result: {
        provider: { id: "provider-openai" },
        models: [],
        discovered: false,
      },
    })
    await waitFor(() => {
      expect(within(openaiCard).getByRole("button", { name: "Save" })).toBeInTheDocument()
    })
    expect(
      within(anthropicCard).getByRole("button", { name: "Saving..." }),
    ).toBeDisabled()

    resolvers.get("anthropic")?.({
      ok: true,
      result: {
        provider: { id: "provider-anthropic" },
        models: [],
        discovered: false,
      },
    })
    await waitFor(() => {
      expect(
        within(anthropicCard).getByRole("button", { name: "Save" }),
      ).toBeInTheDocument()
    })
  })

  it("renders provider setup errors inside the edited card", async () => {
    const setupProvider = vi.fn().mockResolvedValue({
      ok: false,
      error: new Error("Explicit insecure HTTP approval is required"),
    })
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: templates,
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider,
    })

    render(<LlmCatalogPanel />)

    const card = screen.getByRole("group", { name: "OpenAI Compatible" })
    fireEvent.change(within(card).getByLabelText("OpenAI Compatible endpoint"), {
      target: { value: "https://relay.example.com/v1" },
    })
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    expect(
      await within(card).findByText("Explicit insecure HTTP approval is required"),
    ).toBeInTheDocument()
  })

  it("shows a retryable catalog error instead of an empty provider list", () => {
    const refresh = vi.fn()
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: [],
      configuredProviders: [],
      models: [],
      isLoading: false,
      isMutating: false,
      error: new Error("Backend unavailable"),
      refresh,
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    expect(screen.getByText("Providers could not be loaded")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Retry" }))
    expect(refresh).toHaveBeenCalledTimes(1)
  })

  it("renders provider-shaped skeleton rows while loading", () => {
    useLlmCatalogMock.mockReturnValue({
      providerTemplates: [],
      configuredProviders: [],
      models: [],
      isLoading: true,
      isMutating: false,
      error: null,
      refresh: vi.fn(),
      discoverModels: vi.fn(),
      setupProvider: vi.fn(),
    })

    render(<LlmCatalogPanel />)

    expect(screen.getAllByTestId("provider-card-skeleton")).toHaveLength(4)
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
  docsUrl?: string,
) {
  const supportedWireProtocols =
    kind === "openai" || kind === "openai_compatible"
      ? ["chat_completions", "responses"]
      : ["chat_completions"]
  return {
    id,
    name,
    kind,
    docs_url: docsUrl ?? `https://docs.example.com/${id}`,
    discovery,
    default_base_url: defaultBaseUrl,
    supported_wire_protocols: supportedWireProtocols,
    default_wire_protocol: "chat_completions",
    fields,
    models,
  }
}
