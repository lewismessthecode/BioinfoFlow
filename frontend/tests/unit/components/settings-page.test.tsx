import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import SettingsPageClient from "@/components/bioinfoflow/settings/settings-page-client"
import { apiRequest } from "@/lib/api"
import { useAppearance } from "@/lib/appearance/use-appearance"
import { useLlmSettings } from "@/hooks/use-llm-settings"
import { createCelebrationsPreferenceMock } from "@/tests/support/mock-celebrations-preference"

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
const reducedMotionState = { value: false }
const celebrationsPreference = createCelebrationsPreferenceMock()

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pageTitle: "Settings",
      "nav.account": "Account",
      "nav.appearance": "Appearance",
      "nav.providers": "AI Providers",
      "nav.registries": "Container Registries",
      "nav.members": "Members",
      "account.title": "Account details",
      "account.description": "Manage your account.",
      "account.email": "Email",
      "account.role": "Role",
      "account.mode": "Mode",
      "account.notAvailable": "Not available",
      "account.modes.personal": "Personal",
      "account.modes.team": "Team",
      "account.modes.dev": "Development",
      "members.roles.owner": "Owner",
      "members.roles.admin": "Admin",
      "members.roles.member": "Member",
      "appearance.title": "Appearance",
      "appearance.description": "Tune app shell colors and mode.",
      "appearance.mode": "Mode",
      "appearance.presets.light": "Light preset",
      "appearance.presets.dark": "Dark preset",
      "appearance.preview.light": "Light preview",
      "appearance.preview.dark": "Dark preview",
      "appearance.celebrations.title": "Quiet celebrations",
      "appearance.celebrations.description": "Show a short, one-time confetti burst when first setup milestones succeed.",
      "appearance.celebrations.enabledLabel": "On",
      "appearance.celebrations.disabledLabel": "Off",
      "appearance.celebrations.preview": "Preview",
      "appearance.celebrations.reducedMotion": "Reduced motion is on, so confetti is paused.",
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
      "providerCards.loading": "Loading providers...",
      "providerCards.summary": "1 configured",
      "providerCards.save": "Save",
      "providerCards.saving": "Saving...",
      "providerCards.apiKeyPlaceholder": "Paste API key",
      "providerCards.savedKeyPlaceholder": "Key saved. Paste a new key to replace it.",
      "providerCards.endpointPlaceholder": "Endpoint URL",
      "providerCards.getApiKey": "Get key",
      "providerCards.configured": "Configured",
      "providerCards.notConfigured": "Not configured",
      "providerCards.noKeyRequired": "No key required",
      "providerCards.ready": "Ready",
      "providerCards.needsSetup": "Setup",
      "providerCards.fromEnv": "From .env",
      "providerCards.keySavedShort": "Key saved",
      "providerCards.saved": "Provider saved",
      "providerCards.saveFailed": "Provider could not be saved",
      "providerCards.refreshModels": "Refresh models",
      "providerCards.refreshingModels": "Refreshing...",
      "providerCards.modelsDiscovered": "1 models found",
      "providerCards.modelsAvailable": "1 models",
      "providerCards.modelsRefreshed": "Models refreshed",
      "providerCards.modelRefreshFailed": "Models could not be refreshed",
      "providerCards.modelIdPlaceholder": "Model ID",
      "registries.title": "Container Registries",
      "registries.description": "Configure private registries",
      "registries.loading": "Loading registries...",
      "registries.empty": "No registries",
      "registries.loadFailed": "Registry load failed",
      "registries.created": "Registry created",
      "registries.saved": "Registry saved",
      "registries.saveFailed": "Registry save failed",
      "registries.deleted": "Registry deleted",
      "registries.deleteFailed": "Registry delete failed",
      "registries.deleteConfirm": "Delete registry?",
      "registries.testOk": "Registry OK",
      "registries.testFailed": "Registry test failed",
      "registries.defaultSaved": "Default saved",
      "registries.defaultBadge": "Default",
      "registries.form.createTitle": "Add registry",
      "registries.form.editTitle": "Edit registry",
      "registries.form.subtitle": "Use an endpoint",
      "registries.form.create": "Add registry",
      "registries.form.save": "Save registry",
      "registries.form.new": "New",
      "registries.fields.name": "Name",
      "registries.fields.endpoint": "Endpoint",
      "registries.fields.namespace": "Namespace",
      "registries.fields.default": "Default",
      "registries.fields.insecure": "HTTP",
      "registries.fields.credentials": "Credentials",
      "registries.fields.envUsername": "Username env",
      "registries.fields.envPassword": "Password env",
      "registries.fields.username": "Username",
      "registries.fields.password": "Password",
      "registries.placeholders.name": "Company Harbor",
      "registries.placeholders.username": "Robot account",
      "registries.placeholders.password": "Password or token",
      "registries.credentials.none": "No credentials",
      "registries.credentials.env": "Environment variables",
      "registries.credentials.stored": "Stored credentials",
      "registries.status.untested": "Untested",
      "registries.status.ok": "OK",
      "registries.status.error": "Error",
      "registries.actions.edit": "Edit",
      "registries.actions.test": "Test",
      "registries.actions.makeDefault": "Make default",
      "registries.actions.delete": "Delete",
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
  celebrateMilestone: vi.fn(),
  isCelebrationsEnabled: () => celebrationsPreference.getEnabled(),
  useCelebrationsEnabledPreference: () =>
    celebrationsPreference.useCelebrationsEnabledPreference(),
  useReducedMotionPreference: () => reducedMotionState.value,
  setCelebrationsEnabled: (enabled: boolean) => {
    celebrationsPreference.setEnabled(enabled)
  },
  subscribeToCelebrationsPreference: (listener: (enabled: boolean) => void) =>
    celebrationsPreference.subscribeToCelebrationsPreference(listener),
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
    window.history.replaceState(null, "", "/settings")
    apiRequestMock.mockReset()
    updateSettingsMock.mockReset()
    testProviderMock.mockClear()
    celebratePreviewMock.mockReset()
    celebrationsPreference.reset()
    reducedMotionState.value = false
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
      if (path === "/llm/configuration") {
        return {
          data: {
            summary: {
              provider_count: 1,
              configured_provider_count: 1,
              available_provider_count: 1,
              model_count: 1,
              profile_count: 1,
            },
            providers: [
              {
                id: "llm-provider-1",
                name: "Local OpenAI Compatible",
                kind: "openai_compatible",
                base_url: "http://localhost:11434/v1",
                api_key_ref: null,
                scope: "workspace",
                workspace_id: "workspace-1",
                user_id: null,
                enabled: true,
                test_status: { success: true, latency_ms: 32 },
                metadata: { providerTemplate: "openai-compatible" },
                credential: {
                  provider_id: "llm-provider-1",
                  source: "env",
                  configured: true,
                  available: true,
                  env_var_name: "LOCAL_MODEL_KEY",
                  fingerprint: null,
                  masked_hint: "env:LOCAL_MODEL_KEY",
                  updated_at: "2026-06-04T00:00:00Z",
                },
                created_at: "2026-06-04T00:00:00Z",
                updated_at: "2026-06-04T00:00:00Z",
              },
            ],
            models: [
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
            profiles: [
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
          },
          meta: undefined,
        }
      }
      if (path === "/llm/provider-templates") {
        return {
          data: providerTemplates(),
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
      if (path === "/llm/provider-setups" && options?.method === "POST") {
        expect(options.body).toContain('"template_id":"openrouter"')
        expect(options.body).toContain("sk-openrouter")
        return {
          data: {
            provider: {
              id: "llm-provider-2",
              name: "OpenRouter",
              kind: "openrouter",
              base_url: "https://openrouter.ai/api/v1",
              api_key_ref: null,
              scope: "user",
              workspace_id: "workspace-1",
              user_id: "owner-1",
              enabled: true,
              test_status: null,
              metadata: { providerTemplate: "openrouter" },
              credential: {
                provider_id: "llm-provider-2",
                source: "stored",
                configured: true,
                available: true,
                env_var_name: null,
                fingerprint: "fp_openrouter",
                masked_hint: "sk-...uter",
                updated_at: "2026-06-04T00:00:01Z",
              },
              created_at: "2026-06-04T00:00:01Z",
              updated_at: "2026-06-04T00:00:01Z",
            },
            models: [],
            discovered: false,
          },
          meta: undefined,
        }
      }
      if (path === "/container-registries" && !options?.method) {
        return {
          data: [
            {
              id: "registry-harbor",
              name: "Lab Harbor",
              endpoint: "http://10.227.4.56:80",
              namespace: "pipeline-dev",
              insecure: true,
              is_default: true,
              credential_source: "stored",
              username_hint: "pipe...-dev",
              last_status: "untested",
              created_at: "2026-06-29T00:00:00Z",
              updated_at: "2026-06-29T00:00:00Z",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/container-registries" && options?.method === "POST") {
        const body = JSON.parse(String(options.body)) as Record<string, unknown>
        expect(body).toEqual({
          name: "Company Harbor",
          endpoint: "http://10.227.4.56:80",
          namespace: "pipeline-dev",
          insecure: true,
          is_default: true,
          credential_source: "stored",
          username: "pipeline-dev",
          password: "secret",
        })
        return {
          data: { id: "registry-new", ...body },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("opens the AI providers section from the section search param", async () => {
    window.history.replaceState(null, "", "/settings?section=providers")
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

    expect(await screen.findByRole("group", { name: "OpenAI Compatible" })).toBeInTheDocument()
    expect(screen.getByText("From .env")).toBeInTheDocument()
  })

  it("manages container registries from the settings page", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "Container Registries" }))

    expect(await screen.findAllByText("Container Registries")).toHaveLength(2)
    expect(await screen.findByText("Lab Harbor")).toBeInTheDocument()
    expect(screen.getByText("http://10.227.4.56:80/pipeline-dev")).toBeInTheDocument()

    fireEvent.change(screen.getByLabelText("Name"), {
      target: { value: "Company Harbor" },
    })
    fireEvent.change(screen.getByLabelText("Endpoint"), {
      target: { value: "http://10.227.4.56:80" },
    })
    fireEvent.change(screen.getByLabelText("Namespace"), {
      target: { value: "pipeline-dev" },
    })
    fireEvent.click(screen.getByLabelText("HTTP"))
    fireEvent.click(screen.getByLabelText("Default"))
    fireEvent.change(screen.getByLabelText("Credentials"), {
      target: { value: "stored" },
    })
    fireEvent.change(await screen.findByLabelText("Username"), {
      target: { value: "pipeline-dev" },
    })
    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    })
    fireEvent.click(screen.getByRole("button", { name: "Add registry" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/container-registries",
        expect.objectContaining({ method: "POST" }),
      )
    })
  })

  it("requires stored credentials when switching an edited registry to stored credentials", async () => {
    apiRequestMock.mockImplementation(async (path, options) => {
      if (path === "/container-registries" && !options?.method) {
        return {
          data: [
            {
              id: "registry-none",
              name: "Lab Harbor",
              endpoint: "http://10.227.4.56:80",
              namespace: "pipeline-dev",
              insecure: true,
              is_default: false,
              credential_source: "none",
              last_status: "untested",
            },
          ],
          meta: undefined,
        }
      }
      if (path === "/llm/configuration") {
        return { data: { summary: {}, providers: [], models: [] }, meta: undefined }
      }
      throw new Error(`Unexpected path: ${path}`)
    })

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

    fireEvent.click(screen.getByRole("button", { name: "Container Registries" }))

    expect(await screen.findByText("Lab Harbor")).toBeInTheDocument()
    fireEvent.click(screen.getByRole("button", { name: "Edit" }))
    fireEvent.change(screen.getByLabelText("Credentials"), {
      target: { value: "stored" },
    })

    const saveButton = await screen.findByRole("button", { name: "Save registry" })
    expect(saveButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Username"), {
      target: { value: "robot$pipeline-dev" },
    })
    expect(saveButton).toBeDisabled()

    fireEvent.change(screen.getByLabelText("Password"), {
      target: { value: "secret" },
    })
    expect(saveButton).not.toBeDisabled()
  })

  it("falls back from the registries section for team members", async () => {
    window.history.replaceState(null, "", "/settings?section=registries")
    render(
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

    expect(await screen.findByText("Account details")).toBeInTheDocument()
    expect(screen.queryByRole("button", { name: "Container Registries" })).not.toBeInTheDocument()
    expect(screen.queryByText("Configure private registries")).not.toBeInTheDocument()
  })

  it("shows provider cards and creates a write-only provider credential", async () => {
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

    fireEvent.click(screen.getByRole("button", { name: "AI Providers" }))

    expect(await screen.findByRole("group", { name: "OpenAI" })).toBeInTheDocument()
    expect(screen.getByRole("group", { name: "OpenRouter" })).toBeInTheDocument()
    expect(screen.queryByText("Bioinformatics agent default")).not.toBeInTheDocument()

    const openRouterCard = screen.getByRole("group", { name: "OpenRouter" })
    fireEvent.change(within(openRouterCard).getByLabelText("OpenRouter API key"), {
      target: { value: "sk-openrouter" },
    })
    fireEvent.click(within(openRouterCard).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/llm/provider-setups",
        expect.objectContaining({
          method: "POST",
          body: expect.stringContaining("sk-openrouter"),
        }),
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

    expect(screen.getByRole("button", { name: "Appearance" })).toBeInTheDocument()
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

    fireEvent.click(screen.getByRole("button", { name: "Appearance" }))

    expect(screen.getByText("Quiet celebrations")).toBeInTheDocument()
    expect(
      screen.getByText("Show a short, one-time confetti burst when first setup milestones succeed."),
    ).toBeInTheDocument()
    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "true")

    fireEvent.click(screen.getByRole("switch"))

    expect(screen.getByRole("switch")).toHaveAttribute("aria-checked", "false")
    expect(screen.getByText("Off")).toBeInTheDocument()
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

    fireEvent.click(screen.getByRole("button", { name: "Appearance" }))
    fireEvent.click(screen.getByRole("button", { name: "Preview" }))

    expect(celebratePreviewMock).toHaveBeenCalledTimes(1)
  })

  it("pauses the settings preview but keeps the celebration switch available for reduced motion", async () => {
    reducedMotionState.value = true
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

    fireEvent.click(screen.getByRole("button", { name: "Appearance" }))

    expect(screen.getByText("Reduced motion is on, so confetti is paused.")).toBeInTheDocument()
    expect(screen.getByRole("button", { name: "Preview" })).toBeDisabled()
    expect(screen.getByRole("switch", { name: "Quiet celebrations" })).not.toBeDisabled()
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
    fireEvent.click(screen.getByRole("button", { name: "Members" }))
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
    fireEvent.click(screen.getByRole("button", { name: "AI Providers" }))
    expect(await screen.findByRole("group", { name: "OpenAI" })).toBeInTheDocument()
    // Members nav item should not exist
    expect(screen.queryByText("Members")).not.toBeInTheDocument()
    expect(screen.queryByText("Members Panel")).not.toBeInTheDocument()
  })
})

function providerTemplates() {
  const field = (
    name: string,
    label: string,
    secret: boolean,
    required: boolean,
    defaultValue?: string,
  ) => ({
    name,
    label,
    secret,
    required,
    placeholder: label,
    default: defaultValue,
  })
  return [
    template("openai", "OpenAI", "openai", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.openai.com/v1"),
    template("anthropic", "Anthropic", "anthropic", "static", [
      field("api_key", "API key", true, true),
    ]),
    template("gemini", "Gemini", "gemini", "static", [
      field("api_key", "API key", true, true),
    ]),
    template("grok", "Grok", "grok", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.x.ai/v1"),
    template("groq", "Groq", "groq", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.groq.com/openai/v1"),
    template("deepseek", "DeepSeek", "deepseek", "openai_models", [
      field("api_key", "API key", true, true),
    ], "https://api.deepseek.com/v1"),
    template("openrouter", "OpenRouter", "openrouter", "openai_models", [
      field("api_key", "API key", true, true),
      field("model_id", "Model ID", false, false),
    ], "https://openrouter.ai/api/v1", [
      providerModel("openrouter/auto", "OpenRouter Auto"),
    ]),
    template("ollama", "Ollama", "ollama", "ollama_tags", [
      field("base_url", "Endpoint", false, true, "http://localhost:11434"),
      field("model_id", "Model ID", false, false),
    ], "http://localhost:11434"),
    template("vllm", "vLLM", "vllm", "openai_models", [
      field("base_url", "Endpoint", false, true, "http://localhost:8000/v1"),
      field("api_key", "API key", true, false),
      field("model_id", "Model ID", false, false),
    ], "http://localhost:8000/v1"),
    template("openai-compatible", "OpenAI Compatible", "openai_compatible", "openai_models", [
      field("base_url", "Endpoint", false, true, "https://api.example.com/v1"),
      field("api_key", "API key", true, false),
      field("model_id", "Model ID", false, false),
    ], "https://api.example.com/v1"),
  ]
}

function template(
  id: string,
  name: string,
  kind: string,
  discovery: string,
  fields: Array<Record<string, unknown>>,
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

function providerModel(id: string, name: string) {
  return {
    id,
    name,
    supports_tools: true,
    supports_streaming: true,
    supports_vision: false,
    supports_json_schema: true,
    supports_reasoning: false,
  }
}
