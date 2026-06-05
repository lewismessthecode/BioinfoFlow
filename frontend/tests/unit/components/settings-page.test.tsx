import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import SettingsPageClient from "@/components/bioinfoflow/settings/settings-page-client"
import { apiRequest } from "@/lib/api"
import { useAppearance } from "@/lib/appearance/use-appearance"
import { useLlmSettings } from "@/hooks/use-llm-settings"

type ProviderTestResult = {
  success: boolean
  error: string | null
  provider: string
  model: string | null
}

const updateSettingsMock = vi.fn()
const testProviderMock = vi.fn(
  async (provider: string): Promise<ProviderTestResult> => ({
    success: true,
    error: null,
    provider,
    model: null,
  }),
)
const celebratePreviewMock = vi.fn()
let celebrationsEnabledState = true
const celebrationSubscribers = new Set<(enabled: boolean) => void>()

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pageTitle: "Settings",
      "nav.account": "Account",
      "nav.appearance": "Appearance",
      "nav.providers": "AI Providers",
      "nav.members": "Members",
      "appearance.title": "Appearance",
      "appearance.description": "Tune app shell colors and mode.",
      "appearance.mode": "Mode",
      "appearance.presets.light": "Light preset",
      "appearance.presets.dark": "Dark preset",
      "appearance.preview.light": "Light preview",
      "appearance.preview.dark": "Dark preview",
      "appearance.celebrations.title": "Celebrations",
      "appearance.celebrations.description": "Show confetti when first-time setup milestones succeed.",
      "appearance.celebrations.enabledLabel": "Enabled",
      "appearance.celebrations.disabledLabel": "Disabled",
      "appearance.celebrations.preview": "Preview confetti",
      "appearance.celebrations.reducedMotion": "Confetti is disabled while reduced motion is enabled.",
      title: "AI Providers",
      subtitle: "Configure providers",
      apiKey: "API Key",
      apiKeyPlaceholder: "Paste your key",
      baseUrl: "Base URL",
      baseUrlPlaceholder: "Enter base URL",
      model: "Model",
      modelPlaceholder: "Enter model",
      testConnection: "Test",
      status: "Status",
      "status.connected": "Connected",
      "status.notConfigured": "Not configured",
      "llmCatalog.title": "Platform LLM catalog",
      "llmCatalog.description": "Manage providers, model capabilities, and model profiles used by AgentCore.",
      "llmCatalog.addProvider": "Add provider",
      "llmCatalog.providerName": "Provider name",
      "llmCatalog.providerKind": "Provider kind",
      "llmCatalog.apiKeyRef": "API key ref",
      "llmCatalog.enabled": "Enabled",
      "llmCatalog.disabled": "Disabled",
      "llmCatalog.testProvider": "Test provider",
      "llmCatalog.disableProvider": "Disable provider",
      "llmCatalog.enableProvider": "Enable provider",
      "llmCatalog.models": "Models",
      "llmCatalog.modelProfiles": "Model profiles",
      "llmCatalog.context": "Context",
      "llmCatalog.maxOutput": "Max output",
      "llmCatalog.tools": "Tools",
      "llmCatalog.streaming": "Streaming",
      "llmCatalog.vision": "Vision",
      "llmCatalog.jsonSchema": "JSON schema",
      "llmCatalog.reasoning": "Reasoning",
      "llmCatalog.noProviders": "No platform providers registered.",
      "llmCatalog.noModels": "No platform models registered.",
      "llmCatalog.noProfiles": "No model profiles registered.",
      "llmCatalog.created": "Provider added",
      "llmCatalog.testPassed": "Provider test passed",
      "llmCatalog.testFailed": "Provider test failed",
      "llmCatalog.updated": "Provider updated",
      "llmCatalog.loadFailed": "Couldn't load platform LLM catalog.",
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: vi.fn(),
}))

vi.mock("@/lib/appearance/use-appearance", () => ({
  useAppearance: vi.fn(),
}))

vi.mock("@/lib/celebrations", () => ({
  celebratePreview: (...args: unknown[]) => celebratePreviewMock(...args),
  isCelebrationsEnabled: () => celebrationsEnabledState,
  isReducedMotionPreferred: () => false,
  setCelebrationsEnabled: (enabled: boolean) => {
    celebrationsEnabledState = enabled
    for (const listener of celebrationSubscribers) {
      listener(enabled)
    }
  },
  subscribeToCelebrationsPreference: (listener: (enabled: boolean) => void) => {
    celebrationSubscribers.add(listener)
    return () => {
      celebrationSubscribers.delete(listener)
    }
  },
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => <span>{provider}</span>,
}))

vi.mock("@/components/bioinfoflow/settings/members-panel", () => ({
  MembersPanel: () => <div>Members Panel</div>,
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

describe("SettingsPage", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const useAppearanceMock = vi.mocked(useAppearance)
  const useLlmSettingsMock = vi.mocked(useLlmSettings)

  beforeEach(() => {
    apiRequestMock.mockReset()
    updateSettingsMock.mockReset()
    testProviderMock.mockClear()
    celebratePreviewMock.mockReset()
    celebrationsEnabledState = true
    celebrationSubscribers.clear()
    vi.stubGlobal("matchMedia", vi.fn().mockReturnValue({
      matches: false,
      media: "(prefers-reduced-motion: reduce)",
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
    useAppearanceMock.mockReturnValue({
      mode: "system",
      resolvedMode: "light",
      lightPreset: "codex",
      darkPreset: "codex",
      activePreset: "codex",
      setMode: vi.fn(),
      setLightPreset: vi.fn(),
      setDarkPreset: vi.fn(),
    })

    useLlmSettingsMock.mockReturnValue({
      settings: {
        provider_credentials: {
          openai: {
            api_key: "sk-a...1234",
            base_url: "https://api.openai.example/v1",
          },
          ollama: {
            base_url: "http://localhost:11434",
            model: "llama3.3",
          },
        },
        selected_provider: "openai",
        selected_model: "gpt-5.4",
        configured_providers: ["openai", "ollama"],
      },
      models: [],
      allModels: [],
      isLoading: false,
      hasConfiguredProvider: true,
      selectedModel: "gpt-5.4",
      updateSettings: updateSettingsMock,
      setSelectedModel: vi.fn(),
      testProvider: testProviderMock,
      refetch: vi.fn(),
    })

    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/providers") {
        return {
          data: [
            {
              id: "openai",
              label: "OpenAI",
              credential_type: "api_key_and_base_url",
              credential_fields: ["api_key", "base_url"],
              base_url: "https://api.openai.com/v1",
              default_model: "gpt-5.4",
            },
            {
              id: "ollama",
              label: "Ollama",
              credential_type: "base_url_only",
              credential_fields: ["base_url", "model"],
              base_url: "http://localhost:11434",
              default_model: "llama3.3",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/llm/providers") {
        return {
          data: [
            {
              id: "llm-provider-1",
              name: "Local OpenAI Compatible",
              kind: "openai_compatible",
              base_url: "http://localhost:11434/v1",
              api_key_ref: "env:LOCAL_MODEL_KEY",
              scope: "workspace",
              workspace_id: "workspace-1",
              user_id: null,
              enabled: true,
              test_status: { success: true, latency_ms: 32 },
              metadata: null,
              created_at: "2026-06-04T00:00:00Z",
              updated_at: "2026-06-04T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/llm/models") {
        return {
          data: [
            {
              id: "llm-model-1",
              provider_id: "llm-provider-1",
              model_id: "local-bio-coder",
              display_name: "Local Bio Coder",
              context_length: 128000,
              max_output_tokens: 8192,
              supports_tools: true,
              supports_streaming: true,
              supports_vision: false,
              supports_json_schema: true,
              supports_reasoning: true,
              default_temperature: null,
              default_top_p: null,
              cost_metadata: null,
              metadata: null,
              created_at: "2026-06-04T00:00:00Z",
              updated_at: "2026-06-04T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/llm/model-profiles") {
        return {
          data: [
            {
              id: "llm-profile-1",
              name: "Bioinformatics agent default",
              task_type: "agent_core",
              primary_model_id: "llm-model-1",
              fallback_model_ids: [],
              reasoning_budget: 4096,
              max_tokens: 8192,
              cost_ceiling: null,
              routing_policy: { fallback: "on_error" },
              permission_overrides: null,
              scope: "workspace",
              workspace_id: "workspace-1",
              user_id: null,
              enabled: true,
              metadata: null,
              created_at: "2026-06-04T00:00:00Z",
              updated_at: "2026-06-04T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/llm/providers/llm-provider-1/test") {
        return {
          data: {
            provider_id: "llm-provider-1",
            success: true,
            model: "local-bio-coder",
            error: null,
            latency_ms: 31,
          },
          meta: undefined,
        }
      }
      if (path === "/llm/providers" && options?.method === "POST") {
        return {
          data: {
            id: "llm-provider-2",
            name: "OpenRouter Shared",
            kind: "openrouter",
            base_url: "https://openrouter.ai/api/v1",
            api_key_ref: "env:OPENROUTER_API_KEY",
            scope: "workspace",
            workspace_id: "workspace-1",
            user_id: null,
            enabled: true,
            test_status: null,
            metadata: null,
            created_at: "2026-06-04T00:00:01Z",
            updated_at: "2026-06-04T00:00:01Z",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("shows base-url-only providers and supports editing non-key fields", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    // Navigate to AI Providers section
    fireEvent.click(screen.getByText("AI Providers"))

    expect(await screen.findByText("OpenAI")).toBeInTheDocument()
    expect(screen.getByText("Ollama")).toBeInTheDocument()

    const openaiBaseUrl = await screen.findByLabelText("OpenAI Base URL")
    const ollamaModel = screen.getByLabelText("Ollama Model")

    fireEvent.focus(openaiBaseUrl)
    fireEvent.change(openaiBaseUrl, {
      target: { value: "https://proxy.openai.example/v1" },
    })
    fireEvent.blur(openaiBaseUrl)

    await waitFor(() => {
      expect(updateSettingsMock).toHaveBeenCalledWith({
        provider_credentials: {
          openai: {
            base_url: "https://proxy.openai.example/v1",
          },
        },
      })
    })

    fireEvent.focus(ollamaModel)
    fireEvent.change(ollamaModel, { target: { value: "mistral" } })
    fireEvent.blur(ollamaModel)

    await waitFor(() => {
      expect(updateSettingsMock).toHaveBeenCalledWith({
        provider_credentials: {
          ollama: {
            model: "mistral",
          },
        },
      })
    })
  })

  it("shows the platform LLM catalog and supports provider test and creation", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    fireEvent.click(screen.getByText("AI Providers"))

    expect(await screen.findByText("Platform LLM catalog")).toBeInTheDocument()
    expect(screen.getByText("Local OpenAI Compatible")).toBeInTheDocument()
    expect(screen.getAllByText("Local Bio Coder").length).toBeGreaterThan(0)
    expect(screen.getByText("Bioinformatics agent default")).toBeInTheDocument()

    fireEvent.click(screen.getByRole("button", { name: "Test provider" }))
    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/llm/providers/llm-provider-1/test",
        { method: "POST" },
      )
    })

    fireEvent.change(screen.getByLabelText("Provider name"), {
      target: { value: "OpenRouter Shared" },
    })
    fireEvent.change(screen.getByLabelText("Provider kind"), {
      target: { value: "openrouter" },
    })
    fireEvent.change(
      screen.getByLabelText("Base URL", {
        selector: "input#llm-provider-base-url",
      }),
      {
        target: { value: "https://openrouter.ai/api/v1" },
      },
    )
    fireEvent.change(screen.getByLabelText("API key ref"), {
      target: { value: "env:OPENROUTER_API_KEY" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Add provider" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/llm/providers",
        expect.objectContaining({ method: "POST" }),
      )
    })
  })

  it("shows an appearance section in the settings navigation", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    expect(screen.getByText("Appearance")).toBeInTheDocument()
  })

  it("shows celebration controls in appearance and persists the preference", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    fireEvent.click(screen.getByText("Appearance"))

    expect(screen.getByText("Celebrations")).toBeInTheDocument()
    expect(
      screen.getByText("Show confetti when first-time setup milestones succeed."),
    ).toBeInTheDocument()
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true")

    fireEvent.click(screen.getByRole("switch"))

    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false")
    expect(screen.getByText("Disabled")).toBeInTheDocument()
  })

  it("previews confetti from the appearance section", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    fireEvent.click(screen.getByText("Appearance"))
    fireEvent.click(screen.getByRole("button", { name: "Preview confetti" }))

    expect(celebratePreviewMock).toHaveBeenCalledTimes(1)
  })

  it("shows the members panel only to admins and owners", async () => {
    const { rerender } = render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    // Navigate to Members section
    fireEvent.click(screen.getByText("Members"))
    expect(await screen.findByText("Members Panel")).toBeInTheDocument()

    rerender(
      <SettingsPageClient
        viewer={{
          id: "member-1",
          role: "member",
          mode: "team",
          canManageMembers: false,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    // Members nav item should not be visible for non-admins
    expect(screen.queryByText("Members Panel")).not.toBeInTheDocument()
  })

  it("hides the members panel in personal mode even for owners", async () => {
    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          role: "owner",
          mode: "personal",
          canManageMembers: false,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    // Navigate to AI Providers section
    fireEvent.click(screen.getByText("AI Providers"))
    expect(await screen.findByText("OpenAI")).toBeInTheDocument()
    // Members nav item should not exist
    expect(screen.queryByText("Members")).not.toBeInTheDocument()
    expect(screen.queryByText("Members Panel")).not.toBeInTheDocument()
  })
})
