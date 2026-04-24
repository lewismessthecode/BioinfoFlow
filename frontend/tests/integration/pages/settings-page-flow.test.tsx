import { fireEvent, render, screen, waitFor, within } from "@testing-library/react"
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

    apiRequestMock.mockImplementation(async (path) => {
      if (path === "/providers") {
        return {
          data: [
            {
              id: "openai",
              label: "OpenAI",
              credential_type: "api_key_and_base_url",
              credential_fields: ["api_key", "base_url", "model"],
              base_url: "https://api.openai.com/v1",
              default_model: "gpt-5.4",
            },
          ],
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

  it("loads provider cards, saves field edits, and reports both successful and failed connection tests", async () => {
    const user = userEvent.setup()
    testProviderMock
      .mockResolvedValueOnce({
        success: true,
        error: null,
        provider: "openai",
        model: "gpt-5.4",
      })
      .mockResolvedValueOnce({
        success: false,
        error: "Upstream 503",
        provider: "openai",
        model: null,
      })

    const { container } = render(
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
    expect(await screen.findByText("OpenAI")).toBeInTheDocument()

    const baseUrlInput = screen.getByLabelText("OpenAI Base URL")
    await user.click(baseUrlInput)
    await user.clear(baseUrlInput)
    await user.type(baseUrlInput, "https://proxy.internal/v1")
    fireEvent.blur(baseUrlInput)

    await waitFor(() => {
      expect(updateSettingsMock).toHaveBeenCalledWith({
        provider_credentials: {
          openai: {
            base_url: "https://proxy.internal/v1",
          },
        },
      })
    })

    const providerCard = screen.getByText("OpenAI").closest("[data-slot='card']")
    expect(providerCard).not.toBeNull()

    const testButton = within(providerCard!).getByRole("button", { name: "testConnection" })

    await user.click(testButton)
    await waitFor(() => {
      expect(testProviderMock).toHaveBeenCalledWith("openai")
      expect(toastSuccessMock).toHaveBeenCalledWith("Connection succeeded")
      expect(container.querySelector("svg.text-green-500")).not.toBeNull()
    })

    await user.click(testButton)
    await waitFor(() => {
      expect(testProviderMock).toHaveBeenCalledTimes(2)
      expect(toastErrorMock).toHaveBeenCalledWith("Upstream 503")
      expect(container.querySelector("svg.text-destructive")).not.toBeNull()
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
