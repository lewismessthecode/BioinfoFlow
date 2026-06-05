import { fireEvent, render, screen, waitFor } from "@testing-library/react"
import userEvent from "@testing-library/user-event"
import { beforeEach, describe, expect, it, vi } from "vitest"

import type { ProviderField } from "@/components/bioinfoflow/settings/provider-card"

const {
  toastSuccessMock,
  toastErrorMock,
  emitReadinessRefreshMock,
} = vi.hoisted(() => ({
  toastSuccessMock: vi.fn(),
  toastErrorMock: vi.fn(),
  emitReadinessRefreshMock: vi.fn(),
}))

vi.mock("next-intl", () => ({
  useTranslations: () => (key: string, values?: Record<string, string>) => {
    const labels: Record<string, string> = {
      keySaved: "API key saved",
      keyCleared: "API key cleared",
      clearKey: "Clear API Key",
      testSuccess: "Connection succeeded",
      testFailed: "Connection failed",
      "status.connected": "Connected",
      "status.notConfigured": "Not configured",
    }
    if (key === "settingSaved") return `Saved ${values?.field}`
    if (key === "settingCleared") return `Cleared ${values?.field}`
    if (key === "clearValue") return `Clear ${values?.field}`
    if (key === "getApiKey") return `Get ${values?.provider} key`
    return labels[key] ?? key
  },
}))

vi.mock("sonner", () => ({
  toast: {
    success: (...args: unknown[]) => toastSuccessMock(...args),
    error: (...args: unknown[]) => toastErrorMock(...args),
  },
}))

vi.mock("@/components/bioinfoflow/chat/provider-icons", () => ({
  ProviderIcon: ({ provider }: { provider: string }) => <span>{provider}</span>,
}))

vi.mock("@/lib/readiness-events", () => ({
  emitReadinessRefresh: (...args: unknown[]) => emitReadinessRefreshMock(...args),
}))

import { ProviderCard } from "@/components/bioinfoflow/settings/provider-card"

function renderCard(overrides: Partial<React.ComponentProps<typeof ProviderCard>> = {}) {
  const defaultFields: ProviderField[] = [
    {
      name: "api_key",
      label: "API Key",
      value: "sk-live",
      placeholder: "Paste your key",
      secret: true,
    },
    {
      name: "base_url",
      label: "Base URL",
      value: "https://api.openai.com/v1",
      placeholder: "https://api.openai.com/v1",
    },
    {
      name: "model",
      label: "Model",
      value: "gpt-5.4",
      placeholder: "gpt-5.4",
    },
  ]

  const onUpdateField = vi.fn().mockResolvedValue(undefined)
  const onTest = vi.fn().mockResolvedValue({ success: true, error: null })

  const result = render(
    <ProviderCard
      provider="openai"
      label="OpenAI"
      fields={defaultFields}
      isConfigured
      onUpdateField={onUpdateField}
      onTest={onTest}
      {...overrides}
    />,
  )

  return {
    ...result,
    onUpdateField,
    onTest,
  }
}

describe("ProviderCard", () => {
  beforeEach(() => {
    toastSuccessMock.mockReset()
    toastErrorMock.mockReset()
    emitReadinessRefreshMock.mockReset()
  })

  it("persists edited non-secret fields on blur", async () => {
    const user = userEvent.setup()
    const { onUpdateField } = renderCard()

    const baseUrlInput = screen.getByLabelText("OpenAI Base URL")
    await user.click(baseUrlInput)
    await user.clear(baseUrlInput)
    await user.type(baseUrlInput, "https://proxy.openai.internal/v1")
    fireEvent.blur(baseUrlInput)

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith(
        "base_url",
        "https://proxy.openai.internal/v1",
      )
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Saved Base URL")
  })

  it("does not clear an existing API key just because the user focused and left the field", async () => {
    const user = userEvent.setup()
    const { onUpdateField } = renderCard()

    const apiKeyInput = screen.getByLabelText("OpenAI API Key")
    await user.click(apiKeyInput)
    await user.tab()

    expect(onUpdateField).not.toHaveBeenCalledWith("api_key", "")
    expect(onUpdateField).not.toHaveBeenCalled()
  })

  it("lets the user explicitly clear a saved field", async () => {
    const user = userEvent.setup()
    const { onUpdateField } = renderCard()

    await user.click(screen.getByTitle("Clear Model"))

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith("model", "")
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("Cleared Model")
  })

  it("uses readable semantic colors for the configured status badge", () => {
    renderCard({ isConfigured: true })

    const badge = screen.getByText("Connected")

    expect(badge).toHaveClass("bg-success-muted")
    expect(badge).toHaveClass("text-success")
    expect(badge).not.toHaveClass("bg-primary")
  })

  it("refreshes readiness after a successful API key save", async () => {
    const user = userEvent.setup()
    const emptyKeyFields: ProviderField[] = [
      {
        name: "api_key",
        label: "API Key",
        value: "",
        placeholder: "Paste your key",
        secret: true,
      },
    ]
    const { onUpdateField } = renderCard({ fields: emptyKeyFields, isConfigured: false })

    const apiKeyInput = screen.getByLabelText("OpenAI API Key")
    await user.click(apiKeyInput)
    await user.type(apiKeyInput, "sk-new")
    fireEvent.blur(apiKeyInput)

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith("api_key", "sk-new")
    })
    expect(toastSuccessMock).toHaveBeenCalledWith("API key saved")
    expect(emitReadinessRefreshMock).toHaveBeenCalledWith("provider-key-saved")
  })

  it("refreshes readiness when replacing or clearing an existing API key", async () => {
    const user = userEvent.setup()
    const { onUpdateField } = renderCard()

    const apiKeyInput = screen.getByLabelText("OpenAI API Key")
    await user.click(apiKeyInput)
    await user.type(apiKeyInput, "sk-replacement")
    fireEvent.blur(apiKeyInput)

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith("api_key", "sk-replacement")
    })
    expect(emitReadinessRefreshMock).toHaveBeenCalledWith("provider-key-saved")

    await user.click(screen.getByTitle("Clear API Key"))

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith("api_key", "")
    })
    expect(emitReadinessRefreshMock).toHaveBeenCalledTimes(2)
  })

  it("does not refresh readiness when an API key save fails", async () => {
    const user = userEvent.setup()
    const emptyKeyFields: ProviderField[] = [
      {
        name: "api_key",
        label: "API Key",
        value: "",
        placeholder: "Paste your key",
        secret: true,
      },
    ]
    const onUpdateField = vi.fn().mockRejectedValue(new Error("save failed"))

    renderCard({ fields: emptyKeyFields, isConfigured: false, onUpdateField })

    const apiKeyInput = screen.getByLabelText("OpenAI API Key")
    await user.click(apiKeyInput)
    await user.type(apiKeyInput, "sk-new")
    fireEvent.blur(apiKeyInput)

    await waitFor(() => {
      expect(onUpdateField).toHaveBeenCalledWith("api_key", "sk-new")
    })
    expect(emitReadinessRefreshMock).not.toHaveBeenCalled()
  })

  it("surfaces both successful and failed connection tests on the real card control", async () => {
    const user = userEvent.setup()
    const onTest = vi
      .fn()
      .mockResolvedValueOnce({ success: true, error: null })
      .mockResolvedValueOnce({ success: false, error: "Invalid credentials" })

    const { container } = renderCard({ onTest })
    const button = screen.getByRole("button", { name: "testConnection" })

    await user.click(button)
    await waitFor(() => {
      expect(onTest).toHaveBeenCalledTimes(1)
      expect(toastSuccessMock).toHaveBeenCalledWith("Connection succeeded")
      expect(container.querySelector("svg.text-green-500")).not.toBeNull()
    })

    await user.click(button)
    await waitFor(() => {
      expect(onTest).toHaveBeenCalledTimes(2)
      expect(toastErrorMock).toHaveBeenCalledWith("Invalid credentials")
      expect(container.querySelector("svg.text-destructive")).not.toBeNull()
    })
  })
})
