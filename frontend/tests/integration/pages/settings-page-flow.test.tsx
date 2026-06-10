import { render, screen, waitFor, within } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import SettingsPageClient from "@/components/bioinfoflow/settings/settings-page-client"
import { apiRequest } from "@/lib/api"
import { useAppearance } from "@/lib/appearance/use-appearance"
import { useLlmSettings } from "@/hooks/use-llm-settings"

const {
  updateSettingsMock,
  testProviderMock,
  changePasswordMock,
  toastSuccessMock,
  toastErrorMock,
} = vi.hoisted(() => ({
  updateSettingsMock: vi.fn(),
  testProviderMock: vi.fn(),
  changePasswordMock: vi.fn(),
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      pageTitle: "Settings",
      "nav.account": "Account",
      "nav.appearance": "Appearance",
      "nav.providers": "AI Providers",
      "nav.members": "Members",
      "appearance.title": "Appearance",
      "appearance.description": "Tune app shell colors and mode.",
      "appearance.mode": "Mode",
      "appearance.modes.light": "Light",
      "appearance.modes.dark": "Dark",
      "appearance.modes.system": "System",
      "appearance.presets.light": "Light preset",
      "appearance.presets.dark": "Dark preset",
      "appearance.preview.light": "Light preview",
      "appearance.preview.dark": "Dark preview",
      title: "AI Providers",
      subtitle: "Configure providers",
      apiKey: "API Key",
      apiKeyPlaceholder: "Paste your key",
      baseUrl: "Base URL",
      baseUrlPlaceholder: "Enter base URL",
      model: "Model",
      modelPlaceholder: "Enter model",
      "status.connected": "Connected",
      "status.notConfigured": "Not configured",
      testConnection: "testConnection",
      keySaved: "API key saved",
      keyCleared: "API key cleared",
      testSuccess: "Connection succeeded",
      testFailed: "Connection failed",
      "account.title": "Account",
      "account.description": "Manage your identity",
      "account.email": "Email",
      "account.role": "Role",
      "account.mode": "Mode",
      "account.notAvailable": "Not available",
      "account.changePasswordTitle": "Change password",
      "account.changePasswordDescription": "Rotate your local password.",
      "account.currentPassword": "Current password",
      "account.newPassword": "New password",
      "account.savePassword": "Save password",
      "account.savingPassword": "Saving password",
      "account.passwordChanged": "Password changed",
      "account.passwordChangeFailed": "Password change failed",
      "account.modes.team": "Team",
      "members.roles.owner": "Owner",
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
    }
    if (key === "appearance.activePreset") {
      return `Current preset: ${values?.preset ?? ""}`
    }
    if (key === "settingSaved") return `Saved ${values?.field}`
    if (key === "settingCleared") return `Cleared ${values?.field}`
    if (key === "clearValue") return `Clear ${values?.field}`
    if (key === "getApiKey") return `Get ${values?.provider} key`
    return labels[key] ?? key
  },
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: vi.fn(),
}))

vi.mock("@/lib/appearance/use-appearance", () => ({
  useAppearance: vi.fn(),
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => <span>{provider}</span>,
}))

vi.mock("@/components/bioinfoflow/settings/members-panel", () => ({
  MembersPanel: () => <div>Members Panel</div>,
}))

vi.mock("@/lib/auth-client", () => ({
  authClient: {
    changePassword: (...args: unknown[]) => changePasswordMock(...args),
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api")
  return {
    ...actual,
    apiRequest: vi.fn(),
  }
})

describe("Settings page flow", () => {
  const apiRequestMock = vi.mocked(apiRequest)
  const useAppearanceMock = vi.mocked(useAppearance)
  const useLlmSettingsMock = vi.mocked(useLlmSettings)

  beforeEach(() => {
    updateSettingsMock.mockReset()
    testProviderMock.mockReset()
    changePasswordMock.mockReset()
    toastSuccessMock.mockReset()
    toastErrorMock.mockReset()
    apiRequestMock.mockReset()
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
            api_key: "sk-live",
            base_url: "https://api.openai.com/v1",
            model: "gpt-5.4",
          },
        },
        selected_provider: "openai",
        selected_model: "gpt-5.4",
        configured_providers: ["openai"],
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
                name: "OpenAI",
                kind: "openai",
                base_url: "https://api.openai.com/v1",
                api_key_ref: null,
                scope: "workspace",
                workspace_id: "workspace-1",
                user_id: null,
                enabled: true,
                test_status: { success: true, latency_ms: 42 },
                metadata: null,
                credential: {
                  provider_id: "llm-provider-1",
                  source: "env",
                  configured: true,
                  available: true,
                  env_var_name: "OPENAI_API_KEY",
                  fingerprint: null,
                  masked_hint: "env:OPENAI_API_KEY",
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
                model_id: "gpt-5.4",
                display_name: "GPT-5.4",
                context_length: 1000000,
                max_output_tokens: 16384,
                supports_tools: true,
                supports_streaming: true,
                supports_vision: true,
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
                name: "Agent default",
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
      if (path === "/llm/providers/llm-provider-1/test") {
        return {
          data: {
            provider_id: "llm-provider-1",
            success: true,
            model: "gpt-5.4",
            error: null,
            latency_ms: 42,
          },
          meta: undefined,
        }
      }
      if (path === "/llm/providers" && options?.method === "POST") {
        expect(options.body).toContain('"scope":"user"')
        return {
          data: {
            id: "llm-provider-2",
            name: "OpenRouter Shared",
            kind: "openrouter",
            base_url: "https://openrouter.ai/api/v1",
            api_key_ref: null,
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
      if (path === "/llm/providers/llm-provider-2/credential" && options?.method === "PUT") {
        return {
          data: {
            provider_id: "llm-provider-2",
            source: "env",
            configured: true,
            available: true,
            env_var_name: "OPENROUTER_API_KEY",
            fingerprint: null,
            masked_hint: "env:OPENROUTER_API_KEY",
            updated_at: "2026-06-04T00:00:01Z",
          },
          meta: undefined,
        }
      }
      throw new Error(`Unexpected path: ${path}`)
    })
  })

  it("submits the account password form through the real page shell", async () => {
    const user = userEvent.setup()
    changePasswordMock.mockResolvedValue(undefined)

    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          email: "owner@example.com",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    await user.type(screen.getByLabelText("Current password"), "old-secret")
    await user.type(screen.getByLabelText("New password"), "new-secret")
    await user.click(screen.getByRole("button", { name: "Save password" }))

    await waitFor(() => {
      expect(changePasswordMock).toHaveBeenCalledWith({
        currentPassword: "old-secret",
        newPassword: "new-secret",
        revokeOtherSessions: true,
      })
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Password changed")
  })

  it("loads provider cards and saves a write-only credential", async () => {
    const user = userEvent.setup()

    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          email: "owner@example.com",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    await user.click(screen.getByRole("button", { name: "AI Providers" }))
    expect(await screen.findByRole("group", { name: "OpenAI" })).toBeInTheDocument()
    expect(screen.getByRole("group", { name: "OpenRouter" })).toBeInTheDocument()
    expect(screen.getByText("env:OPENAI_API_KEY")).toBeInTheDocument()
    expect(screen.queryByText("Agent default")).not.toBeInTheDocument()

    const openRouterCard = screen.getByRole("group", { name: "OpenRouter" })
    await user.type(within(openRouterCard).getByLabelText("OpenRouter API key"), "sk-openrouter")
    await user.click(within(openRouterCard).getByRole("button", { name: "Save" }))

    await waitFor(() => {
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/llm/providers",
        expect.objectContaining({ method: "POST" }),
      )
      expect(apiRequestMock).toHaveBeenCalledWith(
        "/llm/providers/llm-provider-2/credential",
        expect.objectContaining({
          method: "PUT",
          body: expect.stringContaining("sk-openrouter"),
        }),
      )
    })
  })

  it("renders the appearance section and the dual preset controls", async () => {
    const user = userEvent.setup()

    render(
      <SettingsPageClient
        viewer={{
          id: "owner-1",
          email: "owner@example.com",
          role: "owner",
          mode: "team",
          canManageMembers: true,
          authEnabled: true,
          authLocalEnabled: true,
        }}
      />,
    )

    await user.click(screen.getByRole("button", { name: "Appearance" }))

    expect(screen.getByText("Tune app shell colors and mode.")).toBeInTheDocument()
    expect(screen.getByText("Current preset: Codex")).toBeInTheDocument()
    expect(screen.getByText("Light preview")).toBeInTheDocument()
    expect(screen.getByText("Dark preview")).toBeInTheDocument()
    expect(screen.getAllByTestId("appearance-preview-shell")).toHaveLength(2)
    expect(screen.getByText("Light preset")).toBeInTheDocument()
    expect(screen.getByText("Dark preset")).toBeInTheDocument()
  })
})
