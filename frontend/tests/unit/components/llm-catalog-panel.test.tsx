import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"

import { LlmCatalogPanel } from "@/components/bioinfoflow/settings/llm-catalog-panel"

const useLlmCatalogMock = vi.fn()
const toastErrorMock = vi.fn()
const toastSuccessMock = vi.fn()
const celebrateMilestoneMock = vi.fn()

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
    celebrateMilestoneMock.mockReset()
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
        allowInsecureHttp: false,
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
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
        discover: true,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
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
        discover: true,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
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
        providerId: undefined,
        name: "vLLM",
        baseUrl: "http://localhost:8000/v1",
        apiKey: "",
        modelIds: ["deepseek_v4"],
        discover: true,
        scope: "user",
        enabled: true,
        allowInsecureHttp: false,
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Provider saved")
    expect(celebrateMilestoneMock).not.toHaveBeenCalled()
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
          base_url: "http://8.129.13.231:8079/v1",
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
      target: { value: "http://8.129.13.231:8079/v1" },
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
    expect(insecureSwitch).not.toBeChecked()
    expect(within(card).getByText("Off")).toBeInTheDocument()
    fireEvent.click(insecureSwitch)
    expect(within(card).getByText("On")).toBeInTheDocument()
    fireEvent.click(within(card).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(setupProvider).toHaveBeenCalledWith({
        templateId: "openai-compatible",
        name: "OpenAI Compatible",
        baseUrl: "http://8.129.13.231:8079/v1",
        apiKey: "relay-key",
        modelIds: ["gpt-5.6-sol"],
        discover: true,
        scope: "user",
        enabled: true,
        allowInsecureHttp: true,
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
      target: { value: "http://8.129.13.231:8079/v1" },
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
