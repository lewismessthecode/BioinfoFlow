import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import { beforeEach, describe, expect, it, vi } from "vitest"
import SettingsPageClient from "@/components/bioinfoflow/settings/settings-page-client"
import { apiRequest } from "@/lib/api"
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

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string) => {
    const labels: Record<string, string> = {
      pageTitle: "Settings",
      "nav.account": "Account",
      "nav.providers": "AI Providers",
      "nav.members": "Members",
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
    }
    return labels[key] ?? key
  },
}))

vi.mock("@/hooks/use-llm-settings", () => ({
  useLlmSettings: vi.fn(),
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
  const useLlmSettingsMock = vi.mocked(useLlmSettings)

  beforeEach(() => {
    apiRequestMock.mockReset()
    updateSettingsMock.mockReset()
    testProviderMock.mockClear()

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

    apiRequestMock.mockImplementation(async (path) => {
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
